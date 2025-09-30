# README转PDF工具使用说明

## 🚀 快速使用

### 方法一：在线工具（最简单）

1. **访问 https://md-to-pdf.com/**
2. **上传README.md文件**
3. **点击Convert下载PDF**

### 方法二：使用本项目的Python脚本

```bash
# 1. 进入tools目录
cd server/tools

# 2. 运行转换脚本（会自动安装依赖）
python md_to_pdf.py

# 这会将 ../README.md 转换为 ../README.pdf
```

#### 自定义转换
```bash
# 指定输入和输出文件
python md_to_pdf.py /path/to/your/readme.md /path/to/output.pdf

# 仅指定输入文件（输出文件自动命名）
python md_to_pdf.py ../README.md
```

### 方法三：使用Pandoc（需要安装）

```bash
# 安装Pandoc
# Windows: choco install pandoc
# macOS: brew install pandoc  
# Ubuntu: sudo apt install pandoc

# 转换命令
pandoc ../README.md -o ../README.pdf
```

## 🎨 输出效果

使用本脚本转换的PDF具有以下特性：

✅ **GitHub风格样式** - 与GitHub显示效果一致
✅ **表格支持** - 完美显示配置表格
✅ **代码高亮** - 代码块语法高亮
✅ **emoji支持** - 保留所有emoji表情
✅ **目录结构** - 保持标题层级结构
✅ **A4页面** - 标准A4大小，适合打印

## 🔧 故障排除

### 依赖安装失败
```bash
# 手动安装依赖
pip install markdown weasyprint pygments

# 使用国内镜像
pip install markdown weasyprint pygments -i https://pypi.tuna.tsinghua.edu.cn/simple/
```

### 字体问题（Linux系统）
```bash
# Ubuntu/Debian
sudo apt install fonts-liberation

# CentOS/RHEL
sudo yum install liberation-fonts
```

## 📄 推荐方案

| 需求 | 推荐方案 | 优点 |
|------|----------|------|
| **一次性转换** | 在线工具 | 无需安装，立即使用 |
| **批量转换** | Python脚本 | 自动化，可定制样式 |
| **专业文档** | Pandoc | 功能强大，格式选择多 |

## 💡 使用建议

1. **首次使用**：推荐在线工具快速体验
2. **经常使用**：建议使用Python脚本或安装Pandoc
3. **团队使用**：可以将脚本集成到CI/CD流程中自动生成文档 