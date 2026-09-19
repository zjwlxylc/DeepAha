# SG2 WMA Producer 兼容契约

SG2 **不要求先升级现有 WMA Prompt 才能工作**。旧 `units / positions / tracks / children` 继续兼容。

当未来 WMA 能输出更稳定结构时，推荐使用以下可选字段。

## 1. 顶层容器别名

系统支持：

- `units`
- `positions`
- `tracks`
- `children`
- `program_tiers`
- `tiers`
- `region_variants`
- `action_units`

这些字段只帮助表达结构，不赋予事实权威。

## 2. 推荐的通用 action_units

```json
{
  "action_units": [
    {
      "source_record_key": "stable-source-key",
      "kind": "GROUP",
      "name": "某项目分组",
      "children": [
        {
          "source_record_key": "stable-child-key",
          "kind": "PROGRAM_TIER",
          "name": "本科生组",
          "facts": []
        }
      ]
    }
  ]
}
```

## 3. 身份优先级

跨版本稳定身份优先使用：

1. `source_record_key`；
2. 明确业务编号/岗位代码；
3. 生产者稳定 ID；
4. 只有上述都没有时，才使用版本绑定的弱 fallback。

运行时 `id=p1/p2/...` 或数组顺序**不能**单独成为跨版本稳定身份。

## 4. kind 合法值

- `GROUP`
- `POSITION`
- `TRACK`
- `PROGRAM_TIER`
- `REGION_VARIANT`
- `DEFAULT_SINGLETON`

未知 kind 不应被客户端擅自升级成资格语义。

## 5. 元数据

Unit 可以可选提供：

- `application_url`
- `official_url`
- `region`
- `summary`

它们用于当前 Unit 的展示投影；普通未知业务字段仍应放进 `facts`，不能因为新增元数据而丢失原文。

## 6. 中文机会类型兼容

旧 WMA 自然语言类型仍会被适配，例如：

- 招聘、校招；
- 竞赛、比赛；
- 科研；
- 奖学金；
- 人才政策、人才补贴、补贴；
- 升学、推免、保研、夏令营；
- 实习、社会实践、实践计划。

这只是分类适配，不是事实认证。
