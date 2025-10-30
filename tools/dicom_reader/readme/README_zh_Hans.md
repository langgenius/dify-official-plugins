# DICOM Reader 插件（拆分工具）

本文件提供简体中文说明。英文文档请参见上级目录的 `README.md`。

## 简介
该插件将 DICOM 能力拆分为多个聚焦的小工具，便于在不同场景下按需调用，且响应体更紧凑。

## 工具概览
- dicom_metadata：提取病人/检查/序列/影像关键元数据，可附加指定标签
- dicom_pixels：像素矩阵统计（形状/类型/基本统计）与可选预览图
- dicom_multiframe：多帧影像解析，返回帧数并可预览指定帧
- dicom_hu_correction：应用 RescaleSlope/Intercept 进行灰度/HU 校正
- dicom_spatial：空间几何信息（像素间距、切片厚度、方向/位置、体素大小等）
- dicom_pixel_ops：基础矩阵操作（归一化、加减、裁剪、对比度拉伸、盒式模糊）
- dicom_stats：统计特征（均值/方差/标准差/直方图），支持矩形 ROI
- dicom_volume：结合间距与阈值掩码估算体积（mm³）与掩码内平均强度
- dicom_threshold_mask：阈值生成二值掩码并输出叠加预览
- dicom_roi：矩形 ROI 区域分析（可返回描边预览）
- dicom_model_input：整理为模型输入形状 [1, C, H, W]（或 NHWC），可选归一化与预览

## 通用参数
- `dicom_file`：待处理的 DICOM Part 10（.dcm）文件
- `frame_index`：多帧数据时使用的 0 基帧索引（若适用）
- `max_preview_edge`：预览图最大边长（32–1024）

## 大文件策略
- 能力允许时使用 `stop_before_pixels` 以控制开销
- 预览图统一采用 PNG，小图优先，单张软上限约 8 MB

## 隐私
详见同目录下 `PRIVACY.md`。
