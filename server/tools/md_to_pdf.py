#!/usr/bin/env python3
"""
Markdown to PDF 转换工具
使用 markdown 和 weasyprint 库将 README.md 转换为 PDF
"""

import os
import sys
import markdown
from weasyprint import HTML, CSS
from pathlib import Path

def install_dependencies():
    """安装所需依赖"""
    import subprocess
    
    dependencies = [
        'markdown',
        'weasyprint',
        'pygments'  # 代码高亮
    ]
    
    for dep in dependencies:
        try:
            __import__(dep)
        except ImportError:
            print(f"正在安装 {dep}...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', dep])

def convert_md_to_pdf(md_file, output_file=None, custom_css=None):
    """
    将Markdown文件转换为PDF
    
    Args:
        md_file: Markdown文件路径
        output_file: 输出PDF文件路径
        custom_css: 自定义CSS样式
    """
    
    # 确定输出文件名
    if output_file is None:
        output_file = Path(md_file).with_suffix('.pdf')
    
    # 读取Markdown文件
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    # 转换Markdown为HTML
    md = markdown.Markdown(extensions=[
        'tables',           # 表格支持
        'fenced_code',      # 代码块支持
        'codehilite',       # 代码高亮
        'toc',              # 目录支持
        'extra'             # 额外功能
    ])
    
    html_content = md.convert(md_content)
    
    # 添加HTML结构和CSS样式
    html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>README</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        h1, h2, h3, h4, h5, h6 {{
            margin-top: 24px;
            margin-bottom: 16px;
            font-weight: 600;
            line-height: 1.25;
        }}
        
        h1 {{ border-bottom: 2px solid #eaecef; padding-bottom: 10px; }}
        h2 {{ border-bottom: 1px solid #eaecef; padding-bottom: 8px; }}
        
        code {{
            background-color: #f6f8fa;
            border-radius: 3px;
            padding: 2px 4px;
            font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
        }}
        
        pre {{
            background-color: #f6f8fa;
            border-radius: 6px;
            padding: 16px;
            overflow: auto;
        }}
        
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 16px 0;
        }}
        
        table th, table td {{
            border: 1px solid #dfe2e5;
            padding: 8px 12px;
            text-align: left;
        }}
        
        table th {{
            background-color: #f6f8fa;
            font-weight: 600;
        }}
        
        blockquote {{
            border-left: 4px solid #dfe2e5;
            padding: 0 16px;
            color: #6a737d;
            margin: 16px 0;
        }}
        
        .emoji {{
            font-style: normal;
        }}
        
        @page {{
            margin: 2cm;
            size: A4;
        }}
        
        {custom_css or ''}
    </style>
</head>
<body>
    {html_content}
</body>
</html>
"""
    
    # 转换为PDF
    try:
        HTML(string=html_template).write_pdf(output_file)
        print(f"✅ PDF已生成：{output_file}")
        return True
    except Exception as e:
        print(f"❌ 转换失败：{e}")
        return False

def main():
    """主函数"""
    # 检查命令行参数
    if len(sys.argv) < 2:
        # 默认转换当前目录的README.md
        md_file = "../README.md"
        if not os.path.exists(md_file):
            print("❌ 找不到README.md文件")
            print("用法：python md_to_pdf.py [markdown文件路径] [输出pdf路径]")
            return
    else:
        md_file = sys.argv[1]
    
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    # 检查文件是否存在
    if not os.path.exists(md_file):
        print(f"❌ 文件不存在：{md_file}")
        return
    
    print(f"📖 正在转换：{md_file}")
    
    try:
        # 安装依赖（如果需要）
        install_dependencies()
        
        # 转换文件
        success = convert_md_to_pdf(md_file, output_file)
        
        if success:
            print("🎉 转换完成！")
        else:
            print("❌ 转换失败")
            
    except Exception as e:
        print(f"❌ 发生错误：{e}")

if __name__ == "__main__":
    main() 