from typing import Any, Generator
import os
import shutil
import requests
from PIL import Image

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class FrameExtractor(Tool):
    def _extract_specific_frames(self, gif_path, output_folder, frame_count=5):
        """
        从GIF中提取特定数量的帧（均匀分布）
        
        Args:
            gif_path (str): GIF文件的路径
            output_folder (str): 保存提取帧的输出文件夹路径
            frame_count (int): 要提取的帧数，默认为5
            
        Returns:
            list: 提取的帧的路径列表
        """
        # 创建输出文件夹（如果不存在）
        os.makedirs(output_folder, exist_ok=True)
        
        # 打开GIF文件
        gif = Image.open(gif_path)
        
        # 获取总帧数
        total_frames = gif.n_frames
        print(f"GIF共有 {total_frames} 帧")
        
        # 计算要提取哪些帧
        if frame_count == 2:
            # 如果只要2帧，则提取首帧和尾帧
            frames_to_extract = [0, total_frames - 1]
        else:
            # 否则均匀分布提取帧
            if frame_count >= total_frames:
                # 如果要提取的帧数大于等于总帧数，则提取所有帧
                frames_to_extract = list(range(total_frames))
            else:
                # 均匀分布提取帧
                step = (total_frames - 1) / (frame_count - 1) if frame_count > 1 else 0
                frames_to_extract = [int(i * step) for i in range(frame_count)]
                # 确保包含最后一帧
                if frames_to_extract[-1] != total_frames - 1:
                    frames_to_extract[-1] = total_frames - 1
        
        # 提取并保存指定的帧
        extracted_paths = []
        for i, frame_idx in enumerate(frames_to_extract):
            gif.seek(frame_idx)
            frame = gif.copy()
            output_path = os.path.join(output_folder, f"frame_{i:03d}.png")
            frame.save(output_path)
            extracted_paths.append(output_path)
            print(f"已保存第 {frame_idx+1}/{total_frames} 帧 (索引 {frame_idx})")
        
        print(f"已提取 {len(extracted_paths)} 帧!")
        return extracted_paths

    def _clean_temp_dir(self, temp_dir):
        """
        清理临时目录
        
        Args:
            temp_dir (str): 临时目录路径
        """
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                print(f"已删除临时目录: {temp_dir}")
        except Exception as e:
            print(f"删除临时目录时出错: {str(e)}")

    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        temp_dir = os.path.join(os.path.dirname(__file__), "temp")
        try:
            input_url = tool_parameters.get("input_url")
            frame_count = int(tool_parameters.get("frame_count", 5))  # 默认提取5帧
            input_type = tool_parameters.get("input_type", "GIF")  # 默认为GIF类型
            
            # 创建临时文件夹
            os.makedirs(temp_dir, exist_ok=True)
            
            # 临时GIF文件路径
            gif_path = os.path.join(temp_dir, "input.gif")
            output_folder = os.path.join(temp_dir, "frames")
            
            # 根据输入类型处理
            if input_type == "GIF":
                # 从URL下载GIF
                response = requests.get(input_url, stream=True)
                if response.status_code == 200:
                    with open(gif_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                else:
                    yield self.create_text_message(f"下载GIF失败 - {input_url}，状态码: {response.status_code}")
            else:
                yield self.create_text_message(f"只支持GIF格式。")
            
            # 提取特定数量的帧
            extracted_paths = self._extract_specific_frames(gif_path, output_folder, frame_count)
            
            # 返回提取的帧
            for path in extracted_paths:
                with open(path, 'rb') as f:
                    frame_content = f.read()
                    yield self.create_blob_message(
                        blob=frame_content, 
                        meta={"mime_type": "image/png"}
                    )
                    
        except Exception as e:
            yield self.create_text_message(f"提取帧时出错: {str(e)}")
        finally:
            # 无论成功还是失败，都清理临时目录
            self._clean_temp_dir(temp_dir)
