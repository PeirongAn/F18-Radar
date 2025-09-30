# 静态文件服务使用指南

## 概述

雷达系统服务器现在支持HTTP静态文件服务，可以直接访问前端已打包的文件。服务器同时提供：
- **静态文件服务**: 直接访问前端应用
- **WebSocket连接**: 实时数据通信

## 使用方法

### 1. 基本使用（推荐）

```bash
# 默认启动HTTP服务器（端口8080），静态文件目录为 ../dist
python main.py

# 或者使用自定义端口
python main.py --http-port 3000
```

启动后可以通过以下方式访问：
- **前端应用**: http://localhost:8080/
- **WebSocket**: ws://localhost:8080/ws

### 2. 自定义静态文件目录

```bash
# 使用相对路径
python main.py --static-dir ../my-frontend-build

# 使用绝对路径
python main.py --static-dir /path/to/your/dist

# 使用其他端口
python main.py --static-dir ../dist --http-port 9000
```

### 3. 仅启动WebSocket服务器（兼容模式）

```bash
# 仅启动WebSocket服务器（端口8765），不提供静态文件服务
python main.py --ws-only
```

## 前端构建

在使用静态文件服务之前，需要先构建前端项目：

```bash
# 在项目根目录执行
npm run build
# 或
pnpm build
```

构建完成后，前端文件会生成到 `dist` 目录中。

## 目录结构示例

```
radar/
├── dist/                    # 前端构建输出目录
│   ├── index.html
│   ├── assets/
│   └── ...
├── server/
│   └── main.py
└── ...
```

## 配置选项

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--static-dir` | `../dist` | 静态文件目录路径 |
| `--http-port` | `8080` | HTTP服务器端口 |
| `--ws-only` | `false` | 仅启动WebSocket服务器 |

## 注意事项

1. **静态文件目录**: 确保指定的静态文件目录存在且包含构建后的前端文件
2. **端口冲突**: 如果默认端口被占用，使用 `--http-port` 指定其他端口
3. **WebSocket连接**: 前端需要连接到 `ws://localhost:PORT/ws` 路径
4. **兼容性**: 使用 `--ws-only` 可以保持与原有WebSocket服务器的兼容性

## 故障排除

### 静态文件无法访问
- 检查 `dist` 目录是否存在且包含 `index.html`
- 确认前端项目已正确构建
- 检查目录路径是否正确

### WebSocket连接失败
- 确认WebSocket连接地址为 `ws://localhost:PORT/ws`
- 检查防火墙设置
- 查看服务器日志获取详细错误信息

### 端口被占用
```bash
# 使用其他端口
python main.py --http-port 3000
``` 