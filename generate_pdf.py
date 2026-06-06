"""将考试 JSON 数据生成 PDF：试卷版（无答案）+ 解析版（含答案）。"""

import argparse
import html
import json
import re
import unicodedata
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"

CHINESE_FONTS = [
    ROOT / "simsun.ttc",
    ROOT / "msyh.ttc",
    Path(r"C:\Windows\Fonts\simsun.ttc"),
    Path(r"C:\Windows\Fonts\msyh.ttc"),
]
ENGLISH_FONTS = [Path(r"C:\Windows\Fonts\times.ttf")]

OCR_FIXES = {
    "critić": "critic",
    "musí": "must",
    "mán": "man",
    "yoğun": "intense",
    "wiii": "will",
}

_fonts_ready = False


def first_existing(paths):
    return next((p for p in paths if p.exists()), None)


def setup_fonts():
    global _fonts_ready
    if _fonts_ready:
        return

    chinese = first_existing(CHINESE_FONTS)
    english = first_existing(ENGLISH_FONTS)

    if not chinese:
        raise FileNotFoundError("未找到中文字体，请安装 simsun.ttc 或 msyh.ttc。")

    pdfmetrics.registerFont(TTFont("ChineseFont", str(chinese)))
    if english:
        pdfmetrics.registerFont(TTFont("EnglishFont", str(english)))

    _fonts_ready = True
    return "EnglishFont" if english else "Times-Roman", "ChineseFont"


def normalize_text(text):
    if not text:
        return ""
    for old, new in OCR_FIXES.items():
        text = text.replace(old, new)
    normalized = unicodedata.normalize("NFKD", text)
    chars = []
    for ch in normalized:
        if unicodedata.combining(ch):
            continue
        if ord(ch) < 128 or ord(ch) > 255:
            chars.append(ch)
        else:
            ascii_ch = ch.encode("ascii", "ignore").decode("ascii")
            chars.append(ascii_ch if ascii_ch else ch)
    return "".join(chars)


def esc(text):
    return html.escape(normalize_text(text), quote=False)


def inline(text):
    text = esc(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def markdown_blocks(text):
    if not text:
        return []

    blocks, items = [], []
    for line in normalize_text(text).split("\n"):
        s = line.strip()
        if not s:
            if items:
                blocks.append("<br/>".join(f"&bull; {x}" for x in items))
                items = []
            continue
        if s.startswith("### "):
            if items:
                blocks.append("<br/>".join(f"&bull; {x}" for x in items))
                items = []
            blocks.append(f"<b>{inline(s[4:])}</b>")
        elif s.startswith("## "):
            if items:
                blocks.append("<br/>".join(f"&bull; {x}" for x in items))
                items = []
            blocks.append(f"<b>{inline(s[3:])}</b>")
        elif re.match(r"^[*\-]\s+", s) or re.match(r"^\d+\.\s+", s):
            items.append(inline(re.sub(r"^([*\-]|\d+\.)\s+", "", s)))
        else:
            if items:
                blocks.append("<br/>".join(f"&bull; {x}" for x in items))
                items = []
            blocks.append(inline(s))

    if items:
        blocks.append("<br/>".join(f"&bull; {x}" for x in items))
    return blocks


BLANK_LINE = "<u>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</u>"

# 句中缺词（OCR/数据未标 {{n}} 时）的常见模式
INLINE_GAP_PATTERNS = [
    (r"\bthe\s+of\b", f"the {BLANK_LINE} of"),
    (r"\bThe\s+may\b", f"The {BLANK_LINE} may"),
    (r"\brates\s*is\b", f"rates {BLANK_LINE} is"),
    (r"\bcontinuing\s+of\b", f"continuing {BLANK_LINE} of"),
    (r"\bfor\s+students\b", f"for {BLANK_LINE} students"),
]


def highlight_blanks(text):
    text = inline(text)
    text = re.sub(r"\{\{(\d+)\}\}", r"<u>&nbsp;&nbsp;&nbsp;&nbsp;\1&nbsp;&nbsp;&nbsp;&nbsp;</u>", text)
    return text.replace("\n\n", "<br/><br/>").replace("\n", "<br/>")


def format_fill_blank(text):
    """为听力/填空题题干插入下划线空位。"""
    text = inline(text)
    text = re.sub(r"\{\{(\d+)\}\}", BLANK_LINE, text)

    for pattern, replacement in INLINE_GAP_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    if BLANK_LINE not in text:
        text = text.rstrip() + f" {BLANK_LINE}"

    return text


def build_styles(english_font, chinese_font):
    base = getSampleStyleSheet()
    defs = {
        "ExamTitle": dict(parent=base["Title"], fontName=english_font, fontSize=18, leading=24, alignment=TA_CENTER, spaceAfter=16),
        "PartTitle": dict(parent=base["Heading1"], fontName=english_font, fontSize=13, leading=18, spaceBefore=10, spaceAfter=8),
        "SectionTitle": dict(parent=base["Heading2"], fontName=english_font, fontSize=11, leading=15, spaceBefore=6, spaceAfter=6),
        "Directions": dict(parent=base["Normal"], fontName=english_font, fontSize=10, leading=14, alignment=TA_JUSTIFY, fontStyle="italic", spaceAfter=10),
        "PassageBody": dict(parent=base["Normal"], fontName=english_font, fontSize=10.5, leading=16, alignment=TA_JUSTIFY, firstLineIndent=20, spaceAfter=6),
        "Question": dict(parent=base["Normal"], fontName=english_font, fontSize=10.5, leading=15, spaceBefore=6, spaceAfter=3),
        "Option": dict(parent=base["Normal"], fontName=english_font, fontSize=10, leading=14, leftIndent=18, spaceAfter=2),
        "WordBank": dict(parent=base["Normal"], fontName=english_font, fontSize=10, leading=14, leftIndent=10, spaceAfter=2),
        "Answer": dict(parent=base["Normal"], fontName=chinese_font, fontSize=9.5, leading=14, leftIndent=10, spaceAfter=2),
        "Explanation": dict(parent=base["Normal"], fontName=chinese_font, fontSize=9.5, leading=15, leftIndent=10, spaceAfter=4),
        "Meta": dict(parent=base["Normal"], fontName=english_font, fontSize=9, leading=12, textColor=colors.grey, spaceAfter=6),
    }
    for name, kwargs in defs.items():
        base.add(ParagraphStyle(name=name, **kwargs))
    return base


def page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Times-Roman", 9)
    canvas.drawCentredString(doc.pagesize[0] / 2, 1.5 * cm, f"- {doc.page} -")
    canvas.restoreState()


def word_bank_table(options, styles):
    rows = []
    for i in range(0, len(options), 2):
        left = f"{options[i]['label']}. {inline(options[i]['text'])}"
        right = f"{options[i + 1]['label']}. {inline(options[i + 1]['text'])}" if i + 1 < len(options) else ""
        rows.append([Paragraph(left, styles["WordBank"]), Paragraph(right, styles["WordBank"])])
    table = Table(rows, colWidths=["48%", "48%"], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return table


def part_name(title):
    m = re.match(r"(Part\s+[IVX]+)", title, re.IGNORECASE)
    return m.group(1) if m else None


def build_story(exam, styles, include_answers):
    story = [
        Paragraph(f"<b>{esc(exam['title'])}</b>", styles["ExamTitle"]),
        HRFlowable(width="100%", thickness=1, color=colors.black),
        Spacer(1, 12),
    ]

    current_part = None
    for section in exam["sections"]:
        part = part_name(section["title"])
        if part and part != current_part:
            if current_part:
                story.append(PageBreak())
            story.append(Paragraph(f"<b>{esc(part)}</b>", styles["PartTitle"]))
            current_part = part

        story.append(Paragraph(esc(section["title"]), styles["SectionTitle"]))

        if section.get("instructions"):
            story.append(Paragraph(f"<b>Directions:</b> {inline(section['instructions'])}", styles["Directions"]))

        if section.get("audioSrc"):
            story.append(Paragraph(f"<b>Audio:</b> {esc(section['audioSrc'])}", styles["Meta"]))

        if section.get("content"):
            for para in normalize_text(section["content"]).split("\n\n"):
                if para.strip():
                    story.append(Paragraph(highlight_blanks(para.strip()), styles["PassageBody"]))
            story.append(Spacer(1, 8))

        if section.get("sharedOptions"):
            story.append(Paragraph("<b>Word Bank</b>", styles["SectionTitle"]))
            story.append(word_bank_table(section["sharedOptions"], styles))
            story.append(Spacer(1, 8))

        for q in section.get("questions", []):
            q_text = normalize_text(q.get("text", "")).strip()
            number = q.get("number", "")

            if q.get("type") == "fill-blank":
                body = format_fill_blank(q_text) if q_text else BLANK_LINE
                prompt = f"<b>{number}.</b> {body}"
            elif q_text:
                prompt = f"<b>{number}.</b> {inline(q_text)}"
            else:
                prompt = f"<b>{number}.</b>"

            story.append(Paragraph(prompt, styles["Question"]))

            for opt in q.get("options", []):
                story.append(Paragraph(f"{opt['label']}. {inline(opt['text'])}", styles["Option"]))

            if include_answers:
                if q.get("correctAnswer"):
                    story.append(Paragraph(f"<b>【答案】</b> {inline(str(q['correctAnswer']))}", styles["Answer"]))
                if q.get("explanation"):
                    story.append(Paragraph("<b>【解析】</b>", styles["Explanation"]))
                    for block in markdown_blocks(q["explanation"]):
                        if block.strip():
                            story.append(Paragraph(block, styles["Explanation"]))

            story.append(Spacer(1, 6))

        if include_answers and section.get("passageAnalysis"):
            analysis = normalize_text(section["passageAnalysis"]).strip()
            if analysis and not analysis.startswith("AI Service Error"):
                story.append(Spacer(1, 6))
                story.append(Paragraph("<b>【篇章分析】</b>", styles["Explanation"]))
                for block in markdown_blocks(analysis):
                    if block.strip():
                        story.append(Paragraph(block, styles["Explanation"]))

        story.extend([Spacer(1, 10), HRFlowable(width="100%", thickness=0.5, color=colors.black), Spacer(1, 10)])

    return story


def write_pdf(story, output_path, title):
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=2.5 * cm,
        leftMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title=title,
    )
    doc.build(story, onFirstPage=page_number, onLaterPages=page_number)


def output_paths(json_path, out_dir):
    stem = Path(json_path).stem
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{stem}_paper.pdf", out_dir / f"{stem}_key.pdf"


def generate_one(json_path, styles, out_dir):
    with open(json_path, encoding="utf-8") as f:
        exam = json.load(f)["exams"][0]

    paper_path, key_path = output_paths(json_path, out_dir)

    write_pdf(build_story(exam, styles, include_answers=False), paper_path, exam["title"])
    print(f"  试卷版: {paper_path.name}")

    write_pdf(build_story(exam, styles, include_answers=True), key_path, exam["title"])
    print(f"  解析版: {key_path.name}")

    return paper_path, key_path


def collect_json_files(input_path):
    path = Path(input_path)
    if path.is_file():
        return [path]
    if path.is_dir():
        files = sorted(path.glob("*.json"))
        if not files:
            raise FileNotFoundError(f"目录中没有 JSON 文件: {path}")
        return files
    raise FileNotFoundError(f"找不到输入路径: {path}")


def generate_all(input_dir=None, out_dir=None):
    setup_fonts()
    english_font, chinese_font = (
        "EnglishFont" if first_existing(ENGLISH_FONTS) else "Times-Roman",
        "ChineseFont",
    )
    styles = build_styles(english_font, chinese_font)

    in_dir = Path(input_dir or INPUT_DIR)
    out_dir = Path(out_dir or OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_files = collect_json_files(in_dir)
    print(f"输入: {in_dir.resolve()}")
    print(f"输出: {out_dir.resolve()}")
    print(f"共 {len(json_files)} 个 JSON 文件\n")

    results = []
    for json_path in json_files:
        print(f"[{json_path.name}]")
        results.append(generate_one(json_path, styles, out_dir))
        print()

    return results


def main():
    parser = argparse.ArgumentParser(
        description="批量将 input/ 目录下的 JSON 生成试卷 PDF 和解析 PDF。"
    )
    parser.add_argument(
        "-i", "--input",
        default=str(INPUT_DIR),
        help="输入 JSON 文件或目录（默认 input/）",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=str(OUTPUT_DIR),
        help="输出目录（默认 output/）",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = ROOT / input_path

    generate_all(input_path, args.output_dir)


if __name__ == "__main__":
    main()
