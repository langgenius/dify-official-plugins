import ast
import csv
import json
import re
import traceback
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Tuple
from typing import List, Optional, Dict, Hashable, Literal
from typing import Union

import chardet
import numpy as np
import pandas as pd
import pingouin
import scipy.stats
import statsmodels.api as sm
from bs4 import BeautifulSoup
from dify_plugin.core.runtime import Session
from dify_plugin.entities.model.llm import LLMModelConfig, LLMResult
from dify_plugin.entities.model.message import SystemPromptMessage, UserPromptMessage
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from tools.ai.invoke_llm import invoke_claude_debugger

AI_DIR = Path(__file__).parent


def get_prompt_template(
    site: Literal["table_filter", "naming_master", "fdq", "classify", "table_interpreter", "answer"]
):
    path_system_prompt_table_filter = "templates/system_prompt_table_filter.xml"
    path_system_prompt_naming_master = "templates/system_prompt_naming_master.xml"
    path_system_prompt_fdq = "templates/system_prompt_fdq.xml"
    path_system_prompt_question_classifier = "templates/system_prompt_question_classifier.xml"
    path_system_prompt_table_interpreter = "templates/system_prompt_table_interpreter.xml"
    path_system_prompt_answer = "templates/system_prompt_answer.xml"

    site2path = {
        "table_filter": path_system_prompt_table_filter,
        "naming_master": path_system_prompt_naming_master,
        "fdq": path_system_prompt_fdq,
        "classify": path_system_prompt_question_classifier,
        "table_interpreter": path_system_prompt_table_interpreter,
        "answer": path_system_prompt_answer,
    }

    if site_path := site2path.get(site):
        system_prompt = AI_DIR.joinpath(site_path).read_text(encoding="utf8")
        return system_prompt

    return "You are a helpful AI assistant."


PREVIEW_CODE_WRAPPER = """
<segment>
<question>{question}</question>
<question_type>{question_type}</question_type>
<code>
{query_code}
</code>
<output filename="{recommend_filename}">
{result_markdown}
</output>
</segment>
"""


class QueryStatus(str, Enum):
    """查询状态枚举"""

    SUCCESS = "success"
    ERROR = "error"


class MetaData(BaseModel):
    """查询结果元数据模型"""

    row_count: int = Field(description="结果行数")
    columns: List[str] = Field(description="列名列表")
    dtypes: Dict[Hashable, str] = Field(description="列数据类型")

    class Config:
        json_encoders = {np.dtype: str}


class QueryResult(BaseModel):
    """查询结果模型"""

    timestamp: datetime = Field(default_factory=datetime.now, description="查询时间戳")
    query: str = Field(description="原始查询语句")
    query_type: Optional[str] = Field(default="", description="查询类型")
    query_code: Optional[str] = Field(default="", description="生成的用于操作表格的代码")
    recommend_filename: Optional[str] = Field(default="", description="建议使用的文件名")
    data: List[Dict[str, Any]] = Field(default_factory=list, description="查询结果数据")
    metadata: MetaData = Field(description="结果元数据")
    error: Optional[str] = Field(default=None, description="错误信息")

    class Config:
        json_encoders = {
            np.integer: lambda x: int(x),
            np.floating: float,
            np.ndarray: lambda x: x.tolist(),
            pd.Timestamp: lambda x: x.isoformat(),
            datetime: lambda x: x.isoformat(),
        }

    @field_validator("data", mode="before")
    def convert_nan_to_none(cls, v):
        """将NaN值转换为None"""
        if isinstance(v, list):
            return [{k: None if pd.isna(v) else v for k, v in item.items()} for item in v]
        return v

    def get_recommend_filename(self, suffix: Optional[str] = None):
        """根据查询结果生成文件名建议"""
        name = self.recommend_filename or "output.xlsx"
        if isinstance(suffix, str) and suffix.startswith("."):
            name = f"{Path(name).stem}{suffix}"
        return name.strip()

    def to_llm_ready(self, *, storage_dir: Optional[Path] = None) -> str:
        wrapper_ = PREVIEW_CODE_WRAPPER.format(
            question=self.query,
            question_type=self.query_type,
            query_code=self.query_code,
            recommend_filename=self.get_recommend_filename(suffix=".md"),
            result_markdown=pd.DataFrame.from_records(self.data).to_markdown(index=False),
        ).strip()
        logger.success(f"transformed to LLM ready \n{wrapper_}")

        if isinstance(storage_dir, Path):
            storage_path = storage_dir / self.get_recommend_filename(suffix=".xml")
            storage_path.parent.mkdir(exist_ok=True, parents=True)
            storage_path.write_text(wrapper_, encoding="utf8")

        return wrapper_


class QueryOutputParser:
    """查询结果解析器"""

    @staticmethod
    def parse(
        df_result: Optional[pd.DataFrame],
        query: str,
        *,
        query_type: Optional[str] = "",
        query_code: Optional[str] = "",
        recommend_filename: Optional[str] = "",
        error: Optional[str] = "",
    ) -> QueryResult:
        """将DataFrame结果转换为标准化的Pydantic模型

        Args:
            query_code:
            df_result: 查询返回的DataFrame
            query: 原始查询语句
            error: 错误信息（如果有）
            recommend_filename: 推荐使用的文件名
            query_type:

        Returns:
            QueryResult: 标准化的查询结果模型
        """
        try:
            if isinstance(df_result, (pd.DataFrame, pd.Series)) and not df_result.empty:
                # 将DataFrame转换为字典列表
                data = df_result.to_dict("records")
                metadata = MetaData(
                    row_count=len(data),
                    columns=list(df_result.columns),
                    dtypes={col: str(dtype) for col, dtype in df_result.dtypes.items()},
                )
            elif df_result is not None:
                data = [{"output": f"{df_result}"}]
                metadata = MetaData(row_count=0, columns=[], dtypes={})
            else:
                data = []
                metadata = MetaData(row_count=0, columns=[], dtypes={})

            # 创建查询结果模型
            result = QueryResult(
                query=query,
                query_type=query_type,
                query_code=query_code,
                recommend_filename=recommend_filename,
                data=data,
                metadata=metadata,
                error=error,
            )

            return result

        except Exception as err:
            # 如果解析过程出错，返回错误结果
            error_result = QueryResult(
                query=query,
                query_type=query_type,
                query_code=query_code,
                recommend_filename=recommend_filename,
                data=[],
                metadata=MetaData(row_count=0, columns=[], dtypes={}),
                error=f"结果解析错误: {str(err)}",
            )
            return error_result


AVAILABLE_MODELS = Literal["qwen", "gemini", "coder"]


class TableLoader:
    def __init__(self):
        self.df = None
        self.schema_info = {}
        self.sample_data = []

    @staticmethod
    def _detect_file_encoding(file_path: Path) -> str:
        """检测文件编码"""
        with open(file_path, "rb") as f:
            raw_data = f.read()
            result = chardet.detect(raw_data)
            return result["encoding"]

    @staticmethod
    def _find_valid_table_range(df: pd.DataFrame) -> Tuple[int, int]:
        """查找有效表格的起始和结束行索引"""
        row_counts = df.notna().sum(axis=1)  # 统计每行非空值的数量
        max_count = row_counts.max()

        # 找到数据列数稳定的行范围
        valid_rows = row_counts[row_counts >= max_count * 0.8]  # 允许20%的容差
        start_idx = valid_rows.index[0]
        end_idx = valid_rows.index[-1]

        return start_idx, end_idx

    def _process_excel(self, file_path: Path) -> pd.DataFrame:
        """处理Excel文件"""
        # 首先读取所有数据，不指定header
        return pd.read_excel(file_path, header=None)

    def _process_csv(self, file_path: Path) -> pd.DataFrame:
        """处理CSV文件"""
        encoding = self._detect_file_encoding(file_path)

        # 首先使用csv.reader读取所有行
        with open(file_path, "r", encoding=encoding) as f:
            csv_reader = csv.reader(f)
            rows = list(csv_reader)

        # 转换为DataFrame进行处理
        raw_df = pd.DataFrame(rows)
        start_idx, end_idx = self._find_valid_table_range(raw_df)

        # 提取有效数据范围
        valid_df = raw_df.iloc[start_idx : end_idx + 1].reset_index(drop=True)
        return valid_df

    def format_stock_codes(self, keywords: List[str] = None) -> None:
        """
        扫描DataFrame的列名,对包含关键词且为int类型的列进行格式化:
        1. 转换为str类型
        2. 对非空值补零到6位

        Args:
            keywords: List[str], 默认为 ['证券代码', 'code_id', 'symbol']

        Returns:
            None, 直接修改self.df
        """
        if keywords is None:
            keywords = ["证券代码", "code_id", "symbol"]

        # 获取所有列名
        columns = self.df.columns.tolist()

        # 遍历列名
        for col in columns:
            # 检查列名是否包含关键词
            if any(keyword.lower() in col.lower() for keyword in keywords):
                # 检查数据类型是否为int
                if pd.api.types.is_integer_dtype(self.df[col]):
                    # 转换为字符串类型
                    self.df[col] = self.df[col].astype(str)

                    # 对非空值补零到6位
                    self.df[col] = self.df[col].apply(lambda x: x.zfill(6) if pd.notna(x) else x)

                    logger.debug(f"列 '{col}' 已格式化为6位证券代码")

        return None

    @staticmethod
    def _detect_header_row(df: pd.DataFrame) -> Union[int, None]:
        """
        自动检测表头所在的行。返回行索引（0开始），如果未检测到则返回 None。

        改进的检测规则：
        1. 基础条件：行中非空值数量充足（>50%），且值基本唯一
        2. 数据类型特征：表头通常是字符串类型
        3. 长度特征：表头字符串长度通常适中，不会太长也不会太短
        4. 数值比例：表头行通常不会包含大量数值
        5. 重复值：表头行的重复值应该较少
        """
        max_check_rows = min(15, len(df))
        best_score = -1
        best_row = None

        for idx in range(max_check_rows):
            row = df.iloc[idx]
            score = 0

            # 1. 检查非空值比例和唯一值
            num_non_na = row.notna().sum()
            num_unique = row.nunique()
            non_na_ratio = num_non_na / len(df.columns)

            if non_na_ratio < 0.5:  # 非空值比例过低
                continue

            # 基础分数：非空值比例 * 唯一值比例
            score += non_na_ratio * (num_unique / num_non_na)

            # 2. 检查数据类型
            str_count = sum(1 for x in row if isinstance(x, str))
            str_ratio = str_count / num_non_na
            score += str_ratio * 2  # 字符串比例权重加倍

            # 3. 检查字符串长度
            if str_count > 0:
                str_lengths = [len(str(x)) for x in row if isinstance(x, str)]
                avg_len = sum(str_lengths) / len(str_lengths)
                # 理想的表头长度在2-20之间
                if 2 <= avg_len <= 20:
                    score += 1
                elif avg_len > 50:  # 可能是数据行
                    score -= 1

            # 4. 检查数值比例
            num_count = sum(
                1 for x in row if isinstance(x, (int, float)) and not isinstance(x, bool)
            )
            num_ratio = num_count / num_non_na
            if num_ratio > 0.5:  # 数值比例过高
                score -= 1

            # 5. 检查重复值
            duplicate_ratio = 1 - (num_unique / num_non_na)
            if duplicate_ratio > 0.2:  # 重复值比例过高
                score -= 1

            # 6. 检查特殊标记（可选）
            special_keywords = {
                "序号",
                "编号",
                "名称",
                "代码",
                "日期",
                "id",
                "name",
                "code",
                "date",
            }
            keyword_matches = sum(
                1
                for x in row
                if isinstance(x, str) and any(k in str(x).lower() for k in special_keywords)
            )
            if keyword_matches > 0:
                score += 0.5

            # 更新最佳分数
            if score > best_score:
                best_score = score
                best_row = idx

        # 要求最小分数阈值
        return best_row if best_score >= 1.5 else None

    def _extract_schema_and_samples(self) -> None:
        """提取表格schema信息和样例数据"""

        def _convert_for_json(obj):
            """转换对象使其可JSON序列化"""
            if isinstance(obj, pd.Timestamp):
                return obj.isoformat()
            elif isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, pd.Series):
                return obj.tolist()
            return str(obj)

        # 获取schema信息
        self.schema_info = {
            "columns": list(self.df.columns),
            "dtypes": self.df.dtypes.to_dict(),
            "shape": self.df.shape,
        }

        # 获取随机样例(最多b行)
        sample_size = min(5, len(self.df))
        samples = self.df.sample(n=sample_size).to_dict("records")
        self.sample_data = [
            {k: _convert_for_json(v) for k, v in record.items()} for record in samples
        ]

    def load_table(self, file_path: Union[str, Path]) -> None:
        """Load the table file, process the head and tail comments, and automatically detect the head rows of the table"""
        file_path = Path(file_path)

        if file_path.suffix.lower() == ".csv":
            valid_df = self._process_csv(file_path)
        elif file_path.suffix.lower() in [".xlsx", ".xls"]:
            valid_df = pd.read_excel(file_path, header=None)
        else:
            raise ValueError("Unsupported file formats. Please use table file")

        # 检测表头行
        header_row = self._detect_header_row(valid_df)
        if header_row is not None:
            self.df = valid_df.iloc[header_row:].reset_index(drop=True)
            self.df.columns = valid_df.iloc[header_row]
        else:
            # 默认使用第一行作为表头
            self.df = valid_df.iloc[1:].reset_index(drop=True)
            self.df.columns = valid_df.iloc[0]

        self.format_stock_codes()
        self._extract_schema_and_samples()


class TableQueryEngine:
    def __init__(self, session: Session, dify_model_config: LLMModelConfig):
        self.session = session
        self.dify_model_config = dify_model_config

        self.df = None
        self.schema_info = {}
        self.sample_data = []

    def _invoke_dify_llm(
        self,
        user_content: str,
        system_prompt: str = None,
        temperature: float = 0,
        max_tokens: int = 4096,
    ) -> LLMResult:
        model_config = self.dify_model_config.model_dump().copy()
        model_config["completion_params"] = {"max_tokens": max_tokens, "temperature": temperature}
        return self.session.model.llm.invoke(
            model_config=model_config,
            prompt_messages=[
                SystemPromptMessage(content=system_prompt),
                UserPromptMessage(content=user_content),
            ],
            stream=False,
        )

    def load_table(self, file_path: Union[str, Path]) -> None:
        tl = TableLoader()
        tl.load_table(file_path)

        self.df = tl.df
        self.schema_info = tl.schema_info
        self.sample_data = tl.sample_data

    def pre_classify(self, natural_query: str):
        schemas = {
            "columns": self.schema_info["columns"],
            "dtypes_dict": self.schema_info["dtypes"],
            "shape": self.schema_info["shape"],
            "sample_data": json.dumps(self.sample_data[0], indent=2, ensure_ascii=False),
        }
        system_prompt = f"""
        <task>
        You are a relevance judge, determining whether a user query can be answered using the existing knowledge base. Output "YES" if it is relevant.
        </task>
        <COT>
        Judgment: 1. Is the scenario relevant? 2. Can the question be answered using the following information?
        For example, <not relevant> case: The table is job information related to recruitment data, but the query is to query stock prices.
        For example, <relevant> case: The table is an exam grade sheet, and the query is to query the scores of a subject or calculate the average score of a certain region.
        </COT>
        <schemas>
        Below are the headers, sample data, shape, and description information of the knowledge base tables.
        {schemas}
        </schemas>
        <limitations>
        You can only output "YES" or "NO" and cannot output any other information.
        </limitations>
        """
        runtime_params = {
            "system_prompt": system_prompt,
            "user_content": natural_query,
            "temperature": 0,
            "max_tokens": 512,
        }
        return self._invoke_dify_llm(**runtime_params)

    def second_level_classify(self, natural_query: str):
        schemas = {
            "columns": self.schema_info["columns"],
            "dtypes_dict": self.schema_info["dtypes"],
            "shape": self.schema_info["shape"],
            "sample_data": json.dumps(self.sample_data[0], indent=2, ensure_ascii=False),
        }
        system_prompt = f"""
        <task>
        You are a question classifier, determining whether a user query is a <basic data query> task. Output "YES" if it is.
        </task>
        <COT>
        Judgment: 1. Does the query explicitly request a query? 2. Does the query request a listing of data?
        For example, <not belonging> case: The table is an exam grade sheet, and the query requires calculating the median score of students in a certain region (i.e., data not explicitly given in the grade sheet).
        For example, <belonging> case: The table is an exam grade sheet, and the query is to query the scores of a subject or the scores of students in a certain region.
        </COT>
        <schemas>
        Below are the headers, sample data, shape, and description information of the knowledge base tables.
        {schemas}
        </schemas>
        <limitations>
        You can only output "YES" or "NO" and cannot output any other information.
        </limitations>
        """
        runtime_params = {
            "system_prompt": system_prompt,
            "user_content": natural_query,
            "temperature": 0,
            "max_tokens": 512,
        }
        return self._invoke_dify_llm(**runtime_params)

    def get_query_classification(self, natural_query: str) -> str:
        system_prompt = get_prompt_template("classify")
        user_content = natural_query

        runtime_params = {
            "system_prompt": system_prompt,
            "user_content": user_content,
            "temperature": 0,
            "max_tokens": 512,
        }

        return self._invoke_dify_llm(**runtime_params)

    def gen_related_question(self, question_type: str = "") -> str:
        limitations = ""
        if question_type:
            limitations = f"<question_type>生成的查询类型：{question_type}</question_type>"

        user_content = f"""
        <task>根据表格描述生成自然语言问题</task>
        
        {limitations}
        
        <schemas>
        - columns: {self.schema_info["columns"]}
        - dtypes_dict: {self.schema_info["dtypes"]}
        - shape: {self.schema_info["shape"]}
        </schemas>
        
        <samples>
        {json.dumps(self.sample_data, indent=2, ensure_ascii=False)}
        </samples>
        """

        runtime_params = {
            "system_prompt": get_prompt_template("fdq"),
            "user_content": user_content,
            "temperature": 0.7,
            "max_tokens": 4096,
        }

        return self._invoke_dify_llm(**runtime_params)

    def _generate_query_code(
        self, natural_query: str, agent: Literal["table_filter", "table_interpreter"]
    ) -> str:
        """使用LLM生成查询代码

        Args:
            natural_query: 自然语言查询描述

        Returns:
            str: 生成的Python代码
        """
        system_prompt = get_prompt_template(agent).format(
            columns_list=self.schema_info["columns"],
            dtypes_dict=self.schema_info["dtypes"],
            shape_tuple=self.schema_info["shape"],
            sample_data=json.dumps(self.sample_data, indent=2, ensure_ascii=False),
        )
        user_content = f"<query>{natural_query}<query>"

        # == 提取代码块 == #
        runtime_params = {
            "system_prompt": system_prompt,
            "user_content": user_content,
            "temperature": 0,
            "max_tokens": 4096,
        }

        code = self._invoke_dify_llm(**runtime_params)
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()

        return code

    def _generate_filename(self, natural_query: str, code: str) -> str:
        """生成文件名"""
        system_prompt = get_prompt_template("naming_master")

        user_content = f"""
        <natural_query>
        {natural_query}
        </natural_query>
        <code>
        ```python
        {code}
        ```
        </code>
        """
        runtime_params = {
            "system_prompt": system_prompt,
            "user_content": user_content,
            "temperature": 0.3,
            "max_tokens": 512,
        }

        return self._invoke_dify_llm(**runtime_params)

    def _safe_execute_code(self, code: str) -> Any:
        """安全地执行动态生成的代码

        Args:
            code: 要执行的Python代码

        Returns:
            查询结果
        """
        try:
            # 解析代码确保语法正确
            ast.parse(code)

            # 创建一个隔离的命名空间
            namespace = {
                # 基础库
                "pd": pd,
                "np": np,
                "df": self.df,
                # 统计相关
                "sm": sm,
                "stats": scipy.stats,
                "pingouin": pingouin,
            }

            # 使用exec执行函数定义
            exec(code, namespace)

            # 调用生成的函数
            if "execute_query" not in namespace:
                raise ValueError("生成的代码中没有找到execute_query函数")

            result = namespace["execute_query"](self.df)
            return result

        except Exception as e:
            error_context = {
                "timestamp": datetime.now().isoformat(),
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc(),
            }

            logger.error("代码执行失败", extra={"error_context": error_context})

            return str(traceback.format_exc())

    def query(self, natural_query: str, enable_classifier: bool = True) -> QueryResult:
        """执行自然语言查询并返回标准化的结果

        Args:
            natural_query: todo Natural language query description.
                In multiple rounds of dialogue, this should be a semantic complete query after being spliced by the memory model.
            enable_classifier: Start the problem classifier and let the query flow to `simple query` or `complex calculation`
        Returns:
            QueryResult: Standardized query result model
        """
        if self.df is None:
            return QueryOutputParser.parse(None, natural_query, error="未加载表格数据")

        try:

            # Post-Judgement - Problem Scenario Classification, and then use different branches to generate code
            if enable_classifier:
                # query_type = self.get_query_classification(natural_query)
                is_search = self.second_level_classify(natural_query)
                query_type = "基础数据查询" if "YES" in is_search else "数据统计"
            # Ignore judgment - To the query is the `Basic Data Query` class,
            # guide subsequent workflows to print the results instead of re-investment into memory
            else:
                query_type = "基础数据查询"

            # 生成代码
            if "查询" in query_type:
                query_code = self._generate_query_code(natural_query, "table_filter")
            else:
                query_code = self._generate_query_code(natural_query, "table_interpreter")

            # 安全执行代码
            df_result = None
            for _ in range(3):
                logger.debug(f"[{query_type}]Generate code: \n{query_code}")
                df_result = self._safe_execute_code(query_code)
                if not isinstance(df_result, str):
                    break
                schemas = {
                    "columns": self.schema_info["columns"],
                    "dtypes_dict": self.schema_info["dtypes"],
                    "shape": self.schema_info["shape"],
                    "sample_data": json.dumps(self.sample_data[0], indent=2, ensure_ascii=False),
                }
                question = f"<query>{natural_query}<query>\n<schemas>\n{schemas}\n</schemas>"
                query_code = invoke_claude_debugger(question, query_code, df_result)
                # 检查是否是 markdown 代码块
                if query_code.strip().startswith("```python"):
                    # 使用正则提取代码块内容
                    pattern = r"```python\s*(.*?)\s*```"
                    match = re.search(pattern, query_code, re.DOTALL)
                    if match:
                        query_code = match.group(1).strip()

            # 生成推荐文件名
            recommend_filename = self._generate_filename(natural_query, query_code)

            # 解析并返回结果
            result = QueryOutputParser.parse(
                df_result,
                natural_query,
                query_type=query_type,
                query_code=query_code,
                recommend_filename=recommend_filename,
            )
            return result

        except Exception as err:
            return QueryOutputParser.parse(pd.DataFrame(), natural_query, error=str(err))

    def answer(self, natural_query: str, __context__: str) -> str:
        """LLM 根据表格操作结果回复自然语言查询"""
        soup = BeautifulSoup(__context__, "lxml")
        if "基础数据查询" in soup.find("question_type").string:
            return soup.find("output").string.strip()

        system_prompt = get_prompt_template("answer").format(context=__context__)

        runtime_params = {
            "system_prompt": system_prompt,
            "user_content": natural_query,
            "temperature": 0,
            "max_tokens": 4096,
        }

        return self._invoke_dify_llm(**runtime_params)
