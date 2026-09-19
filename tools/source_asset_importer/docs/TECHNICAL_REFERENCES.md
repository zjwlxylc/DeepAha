# 技术文档依据

业务要求以本包 docs/baseline 中的用户项目文件为依据。以下官方技术资料仅用于程序实现，不用它们替换或补造 DeepAha 业务事实。

- Python tkinter：图形事件与线程模型。`https://docs.python.org/3/library/tkinter.html`
- Python sqlite3：显式事务控制。`https://docs.python.org/3.11/library/sqlite3.html`
- Python urllib.request：请求、HTTPS和重定向处理。`https://docs.python.org/3/library/urllib.request.html`
- Psycopg3：事务与连接行为。`https://www.psycopg.org/psycopg3/docs/basic/transactions.html`
- FastAPI：已有应用的适配思路。`https://fastapi.tiangolo.com/advanced/wsgi/`

本实现的默认运行路径没有依赖 SQLAlchemy，也不使用任何 SDK 向模型发送信息。可选依赖的安装范围不是“已在真实部署环境测试”的证明；具体本地测试版本见验证报告。
