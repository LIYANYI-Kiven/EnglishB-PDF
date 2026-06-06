# EnglishB-PDF

将英语考试 JSON 数据批量生成 PDF。

## 目录结构

```
EnglishB-PDF/
├── input/           # 放入 JSON 试卷数据
├── output/          # 生成的 PDF（自动创建）
├── generate_pdf.py
└── requirements.txt
```

## 使用

```bash
pip install -r requirements.txt
python generate_pdf.py
```

将 JSON 文件放入 `input/` 后运行，程序会在 `output/` 为每个 JSON 生成两份 PDF：

| 文件 | 说明 |
|------|------|
| `*_paper.pdf` | 试卷版（无答案、无解析） |
| `*_key.pdf` | 解析版（含答案与解析） |

例如 `input/Model_Test_1.json` 会生成：

- `output/Model_Test_1_paper.pdf`
- `output/Model_Test_1_key.pdf`

## 可选参数

```bash
# 指定输入目录和输出目录
python generate_pdf.py -i input -o output

# 只处理单个 JSON 文件
python generate_pdf.py -i input/Model_Test_1.json
```
