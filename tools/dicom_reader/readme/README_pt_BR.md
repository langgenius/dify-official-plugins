# Plugin DICOM Reader (Ferramentas divididas)

Este arquivo fornece documentação em português. Para a documentação em inglês, consulte `README.md` no diretório superior.

## Introdução
Este plugin divide as capacidades DICOM em ferramentas focadas, permitindo usar apenas o que você precisa. As respostas são compactas e ideais para LLMs.

## Ferramentas
- dicom_metadata: metadados de paciente/estudo/série/imagem; suporta tags adicionais
- dicom_pixels: resumo da matriz de pixels (forma/tipo/estatísticas) e prévia opcional
- dicom_multiframe: análise de multiframe, número de quadros e prévia
- dicom_hu_correction: correção usando RescaleSlope/Intercept (HU aproximado)
- dicom_spatial: informações espaciais (PixelSpacing, SliceThickness, orientação/posição, voxel)
- dicom_pixel_ops: operações básicas (normalizar, somar/subtrair, clip, esticar contraste, box blur)
- dicom_stats: estatísticas (média/variância/desvio/Hist) com ROI retangular
- dicom_volume: volume (mm³) estimado com espaçamento × máscara por limiar; média no mask
- dicom_threshold_mask: máscara binária por limiar e sobreposição
- dicom_roi: análise de ROI retangular (prévia com contorno)
- dicom_model_input: forma padrão para modelos [1, C, H, W] (ou NHWC), normalização e prévia

## Parâmetros comuns
- `dicom_file`: arquivo DICOM Part 10 (.dcm)
- `frame_index`: índice (base 0) para multiframe (quando aplicável)
- `max_preview_edge`: lado máximo da prévia (32–1024)

## Arquivos grandes
- Usa `stop_before_pixels` quando possível para reduzir custo
- Prévias em PNG com limite brando de ~8 MB por imagem

## Privacidade
Consulte `PRIVACY.md` no mesmo diretório.
