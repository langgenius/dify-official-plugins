import json
import operator
from typing import Any, Union
from collections.abc import Generator

import nltk
import sacrebleu
import jieba
from nltk.translate.meteor_score import meteor_score
from nltk.translate.nist_score import corpus_nist
from nltk.corpus import wordnet as wn
import statistics
import boto3

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

def tokenize_zh(text):
    return list(jieba.cut(text))

def calculate_bleu(references, hypotheses , weights=(0.25, 0.25, 0.25, 0.25)):
    reference_tokenized = [[ " ".join(tokenize_zh(ref)) for ref in references]]
    hypothesis_tokenized = [" ".join(tokenize_zh(hypotheses))]

    bleu = sacrebleu.corpus_bleu(hypothesis_tokenized, reference_tokenized)

    return bleu.score

# def chinese_synonyms(word):
#     synonyms = set()
#     # 尝试从WordNet获取同义词
#     for synset in wn.synsets(word, lang='cmn'):
#         for lemma in synset.lemmas(lang='cmn'):
#             synonyms.add(lemma.name())
    
#     return synonyms

# 创建自定义的METEOR评分函数，支持中文
def chinese_meteor_score(references, hypothesis, alpha=0.9, beta=3.0, gamma=0.5):
    # 分词
    tokenized_references = [tokenize_zh(ref) for ref in references]
    tokenized_hypothesis = tokenize_zh(hypothesis)
    
    # 调用NLTK的meteor_score，并提供中文同义词查找函数
    score = meteor_score(
        tokenized_references, 
        tokenized_hypothesis,
        alpha=alpha,
        beta=beta,
        gamma=gamma
    )
    
    return score

def calculate_nist(references, hypotheses):
    try:
        tokenized_references = [[ tokenize_zh(ref) for ref in references]]
        tokenized_hypothesis = [tokenize_zh(hypotheses)]
        score = corpus_nist(tokenized_references, tokenized_hypothesis)
    except Exception as e:
        score = None

    return score

def evaluate_with_metric(references, hypotheses):
    sacrebleu, meteor_score, nist_score = None, None, None
    try:
        sacrebleu = calculate_bleu(references, hypotheses)
        meteor_score = chinese_meteor_score(references, hypotheses)
        nist_score = calculate_nist(references, hypotheses)
    except Exception as e:
        print(f"Exception: {e}")

    return {
        'sacrebleu': sacrebleu,
        'meteor':  meteor_score,
        'nist': nist_score
    }

def evaluate_with_model(sagemaker_endpoint, source, translation):
    return {}
    
class TranslationEvalTool(Tool):
    init_state: bool = False
    sagemaker_endpoint: str = None

    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage]:
        """
        invoke tools
        """
        try:
            if self.init_state == False:
                # 确保下载必要的NLTK资源
                try:
                    #nltk.data.find('tokenizers/punkt')
                    nltk.data.find('wordnet')
                    nltk.data.find('omw-1.4')
                except LookupError:
                    #nltk.download('punkt')
                    nltk.download('wordnet')
                    nltk.download('omw-1.4') 
                self.init_state= True

            eval_result = {}
            source = tool_parameters.get("source")
            translation = tool_parameters.get("translation")
            label = tool_parameters.get("label")
            model_endpoint = tool_parameters.get("model_endpoint")
            if model_endpoint:
                result = evaluate_with_model(self.sagemaker_endpoint, source, translation)
                eval_result["model_diagnose"] = result

            if translation and label:
                references = [label]
                hypotheses = translation
                result = evaluate_with_metric(references, hypotheses)
                eval_result["metric"] = result

            yield self.create_json_message(eval_result)

        except Exception as e:
            yield self.create_text_message(f"Exception: {str(e)}")