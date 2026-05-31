#!/usr/bin/env python3
"""
Word 文档企业信息导入脚本
用法: python scripts/import_word.py <word文件路径>
示例: python scripts/import_word.py "C:/Users/Desktop/企业资料.docx"

说明: 使用 Python 标准库直接解析 .docx（ZIP+XML），无需安装 python-docx
"""

import sys
import os
import re
import zipfile
import xml.etree.ElementTree as ET
import uuid
from datetime import datetime, timezone

# 确保能找到 backend 目录下的模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.core.database import sync_engine, Base
from app.models.project import Project
from app.models.brand import Brand
from app.models.brand_fact import BrandFact
from app.models.corpus_item import CorpusItem

# 确保表已存在（开发环境自动建表）
Base.metadata.create_all(sync_engine)


# === 自动提取规则 ===
PHONE_PATTERN = re.compile(r"(?:电话|联系方式|Tel|Phone|手机|咨询热线|客服)[:：\s]*([\d\-()（）\s+]{7,20})")
MOBILE_PATTERN = re.compile(r"1[3-9]\d{9}")
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
URL_PATTERN = re.compile(r"https?://[a-zA-Z0-9.-]+(?:/[\w./-]*)?")
ADDRESS_PATTERN = re.compile(r"(?:地址|所在地|Location|公司地址|总部)[:：\s]*([^\n]{5,80})")


def read_docx_stdlib(file_path: str) -> tuple:
    """使用标准库读取 Word 文档，返回 (标题, 全文, 段落列表)"""
    paragraphs = []
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    with zipfile.ZipFile(file_path, "r") as zf:
        # 读取文档正文
        if "word/document.xml" not in zf.namelist():
            raise ValueError("无效的 .docx 文件，找不到 word/document.xml")

        xml_content = zf.read("word/document.xml")
        root = ET.fromstring(xml_content)

        # 遍历所有段落 <w:p>
        for paragraph in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
            texts = []
            for node in paragraph.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
                if node.text:
                    texts.append(node.text)
            para_text = "".join(texts).strip()
            if para_text:
                paragraphs.append(para_text)

    full_text = "\n".join(paragraphs)

    # 尝试读取 core.xml 获取文档标题
    title = ""
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            if "docProps/core.xml" in zf.namelist():
                core_xml = zf.read("docProps/core.xml")
                core_root = ET.fromstring(core_xml)
                # core.xml 使用 dc 命名空间
                for title_node in core_root.iter():
                    if title_node.tag.endswith("}title"):
                        title = (title_node.text or "").strip()
                        break
    except Exception:
        pass

    if not title and paragraphs:
        title = paragraphs[0][:50]
    if not title:
        title = os.path.splitext(os.path.basename(file_path))[0]

    return title, full_text, paragraphs


def extract_info(text: str) -> dict:
    """从文本中提取关键企业信息"""
    info = {
        "phones": [],
        "emails": [],
        "urls": [],
        "addresses": [],
    }

    # 电话（带标签）
    for m in PHONE_PATTERN.finditer(text):
        info["phones"].append(m.group(1).strip())
    # 手机号
    for m in MOBILE_PATTERN.finditer(text):
        phone = m.group(0).strip()
        if phone not in info["phones"]:
            info["phones"].append(phone)

    # 邮箱
    for m in EMAIL_PATTERN.finditer(text):
        info["emails"].append(m.group(0).strip())

    # 网址
    for m in URL_PATTERN.finditer(text):
        url = m.group(0).strip()
        if url not in info["urls"]:
            info["urls"].append(url)

    # 地址
    for m in ADDRESS_PATTERN.finditer(text):
        info["addresses"].append(m.group(1).strip())

    # 去重
    for key in info:
        seen = set()
        unique = []
        for item in info[key]:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        info[key] = unique

    return info


def ask(prompt: str, default: str = "") -> str:
    """交互式输入"""
    if default:
        user_input = input(f"{prompt} [{default}]: ").strip()
        return user_input if user_input else default
    return input(f"{prompt}: ").strip()


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/import_word.py <word文件路径>")
        print("示例: python scripts/import_word.py \"C:/Users/Desktop/企业资料.docx\"")
        sys.exit(1)

    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f"❌ 文件不存在: {file_path}")
        sys.exit(1)

    print(f"\n📄 正在读取: {file_path}")
    try:
        title, full_text, paragraphs = read_docx_stdlib(file_path)
    except Exception as e:
        print(f"❌ 读取文档失败: {e}")
        sys.exit(1)

    print(f"✅ 读取完成，共 {len(paragraphs)} 段，约 {len(full_text)} 字符\n")

    # 自动提取信息
    extracted = extract_info(full_text)
    print("🔍 自动检测到以下信息:")
    if extracted["phones"]:
        print(f"   电话: {', '.join(extracted['phones'][:3])}")
    if extracted["emails"]:
        print(f"   邮箱: {', '.join(extracted['emails'][:3])}")
    if extracted["urls"]:
        print(f"   网址: {', '.join(extracted['urls'][:3])}")
    if extracted["addresses"]:
        print(f"   地址: {', '.join(extracted['addresses'][:3])}")
    if not any(extracted.values()):
        print("   (未自动检测到结构化信息)")
    print()

    # 交互式确认项目信息
    print("=" * 50)
    print("  请输入项目基本信息（直接回车使用默认值）")
    print("=" * 50)

    project_name = ask("项目名称", title)
    brand_name = ask("品牌名称", project_name)
    company_name = ask("公司名称", brand_name)
    industry = ask("行业", "education_training")
    region = ask("地区", "本地")

    # 构建官方网址默认值
    default_site = extracted["urls"][0] if extracted["urls"] else ""
    official_site = ask("官网地址", default_site)

    print("\n" + "=" * 50)
    print("  正在写入数据库...")
    print("=" * 50)

    with Session(sync_engine) as db:
        # 1. 创建项目
        project = Project(
            id=str(uuid.uuid4()),
            name=project_name,
            industry=industry,
            region=region,
            status="active",
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        print(f"✅ 项目已创建: {project.name} (ID: {project.id})")

        # 2. 创建品牌
        brand = Brand(
            id=str(uuid.uuid4()),
            project_id=project.id,
            brand_name=brand_name,
            company_name=company_name or None,
            official_site=official_site or None,
            description=paragraphs[0][:200] if paragraphs else None,
        )
        db.add(brand)
        db.commit()
        db.refresh(brand)
        print(f"✅ 品牌已创建: {brand.brand_name} (ID: {brand.id})")

        # 3. 创建语料条目（全文）
        corpus = CorpusItem(
            id=str(uuid.uuid4()),
            project_id=project.id,
            title=title,
            content=full_text,
            source_type="official_document",
            contains_factual_claim=True,
        )
        db.add(corpus)
        db.commit()
        db.refresh(corpus)
        print(f"✅ 语料已创建: {corpus.title} (ID: {corpus.id})")

        # 4. 自动创建品牌事实
        facts_created = 0

        # 电话事实
        for phone in extracted["phones"][:2]:
            fact = BrandFact(
                id=str(uuid.uuid4()),
                brand_id=brand.id,
                fact_type="contact",
                value=phone,
                public_wording=f"联系电话：{phone}",
                fact_scope="public",
                source="Word文档导入",
                status="draft",
            )
            db.add(fact)
            facts_created += 1

        # 邮箱事实
        for email in extracted["emails"][:2]:
            fact = BrandFact(
                id=str(uuid.uuid4()),
                brand_id=brand.id,
                fact_type="contact",
                value=email,
                public_wording=f"联系邮箱：{email}",
                fact_scope="public",
                source="Word文档导入",
                status="draft",
            )
            db.add(fact)
            facts_created += 1

        # 网址事实
        for url in extracted["urls"][:2]:
            fact = BrandFact(
                id=str(uuid.uuid4()),
                brand_id=brand.id,
                fact_type="official_site",
                value=url,
                public_wording=f"官方网站：{url}",
                fact_scope="public",
                source="Word文档导入",
                status="draft",
            )
            db.add(fact)
            facts_created += 1

        # 地址事实
        for addr in extracted["addresses"][:2]:
            fact = BrandFact(
                id=str(uuid.uuid4()),
                brand_id=brand.id,
                fact_type="address",
                value=addr,
                public_wording=f"地址：{addr}",
                fact_scope="public",
                source="Word文档导入",
                status="draft",
            )
            db.add(fact)
            facts_created += 1

        # 品牌简介事实（第一段）
        if paragraphs:
            summary = paragraphs[0][:500]
            fact = BrandFact(
                id=str(uuid.uuid4()),
                brand_id=brand.id,
                fact_type="brand_intro",
                value=summary,
                public_wording=summary,
                fact_scope="public",
                source="Word文档导入",
                status="draft",
            )
            db.add(fact)
            facts_created += 1

        db.commit()
        if facts_created:
            print(f"✅ 自动提取并创建了 {facts_created} 条品牌事实")
        else:
            print("⚠️  未自动提取到品牌事实，请手动在品牌事实库中补充")

    print("\n" + "=" * 50)
    print("  导入完成！")
    print("=" * 50)
    print(f"\n你现在可以打开浏览器查看:")
    print(f"  项目:       http://localhost:3000/projects")
    print(f"  品牌事实库: http://localhost:3000/brand-facts")
    print()


if __name__ == "__main__":
    main()
