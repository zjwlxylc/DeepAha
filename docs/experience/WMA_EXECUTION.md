# WMA 连接、策略与真实验证

## 默认策略

现有 Direct WMA → 已发布 Agent 路径保留。**没有实现或假称支持临时覆盖已发布 Agent 的模型。**不同模型通过宿主登记不同已发布 Agent 连接选择；前端只选择连接，不传 API Key 或模型能力证明。

AGENS / Agnes 为项目明确指定的串行策略，不能被界面验证字段或并发数绕过；未知模型、未知发布绑定、没有匹配 LIVE 验证的其他模型也串行。后台可以暂停新调度、设置1–4并发、同域名上限、队列容量和60–1800秒预算。有效并发还受当前绑定已验证上限与任务创建快照限制。

来源周期任务仍使用 `default` 连接；新建调查可选宿主登记连接。绑定刷新影响新调度；旧排队任务的绑定不一致时停止，要求明确另建，不偷偷切换模型。已发出的任务不会因关闭开关而假装被终止。

## 宿主绑定

`default` 继续使用原有 `DEEPAHA_WMA_AGENT_ID`、`DEEPAHA_WMA_API_KEY`、`DEEPAHA_WMA_SOURCE_APP`、启用开关（以 config.py 为准）。正式密钥仍只在宿主保存。命名绑定可令 `DEEPAHA_WMA_BINDINGS_FILE` 指向**绝对路径** JSON，例如 `/etc/deepaha/wma-bindings.json`：

```json
{
  "bindings": [
    {
      "id": "research",
      "label": "研究调查连接",
      "agent_id_env": "DEEPAHA_WMA_RESEARCH_AGENT_ID",
      "api_key_env": "DEEPAHA_WMA_RESEARCH_API_KEY",
      "source_app": "deepaha",
      "enabled": true
    }
  ]
}
```

JSON 只保存变量名，不填密钥值。参考文件 `infra/experience/wma-bindings.example.json`。禁止在源码、截图、Shell历史或日志里打印实际秘密。

后台“读取发布绑定”只读取发布元数据，不调查；成功不等于调用质量或并发验证通过。实际 Agent/密钥/发布配置变化会改变指纹，之前验证不再授予新的并发能力。

## 真实验证工具：本轮未执行

必须先在可控宿主安装 `backend/requirements-wma.txt`，确认官方平台预算和权限，停止使用相同供应商账户的其他系统/数据库任务。程序只能协调本数据库，不能控制腾讯后台、其他数据库或外部程序的调用。请选择一条已批准的**单公告**，不是整个网站。

命令必须明确调用数量和单任务预算，证据目录必须为新目录：

```bash
python -m deepaha.product.cli validate-wma-live \
  --actor YOUR_OPERATOR --connection research \
  --source YOUR_APPROVED_SOURCE_ID --url https://YOUR_OFFICIAL_NOTICE \
  --parallel 1 --max-prompts 1 --budget-seconds 600 \
  --confirm-paid-validation --evidence-dir /var/lib/deepaha-validation/run-001
```

`--confirm-paid-validation` 会授权真实远程工作，不能当作普通健康检查。`max-prompts` 必须等于1/2/4并发数；预算只限制本次客户端等待，不承诺供应商最终费用或远端强制终止。AGENS禁止并发2/4。其他连接在同一发布绑定**1成功后才能2、2成功后才能4**，每次新目录，数量与耗时上限重新明确。

实测占用同数据库调度通道；已有运行或远端不明任务时拒绝。按真实返回保存 Runtime/Session标识、结果文件、哈希、停止原因和请求重叠区间；结果不进入正式机会库。只有执行工具且当前绑定不变、所有返回机械契约通过时，才新增 LIVE 验证记录和独立 `grant-receipt.json`。

**请求重叠 ≠ 供应商内部计算并发证明；机械契约通过 ≠ 语义准确率。**程序不替腾讯做 SLA 或限额承诺。

## 失败与恢复

报告 FAIL、网络不明或进程中断后，不自动换 prompt 重跑。查看本轮 `report.json`，在 WMA 侧查清其所有会话；未知远端会保留全局调度占用，界面可见。真正确认**本地实测进程也已退出、所有远端会话均结束**后，宿主才可执行：

```bash
python -m deepaha.product.cli resolve-wma-probe \
  --actor YOUR_OPERATOR --confirm-remote-terminal --reason "填写实际核查记录"
```

这只是人工确认后的释放，不会替你终止远端，也不授予并发。普通业务任务用“恢复文件”；只有明确要重新调查才新建任务并消耗新预算。

本包测试通过的是**合成远端的调度机制**。测试里模拟的 LIVE 数据行只存在临时测试数据库，不随包写入你的数据库，不可复制它们作为生产验证记录。
