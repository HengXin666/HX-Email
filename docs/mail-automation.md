# 邮件轮询与转发

## 触发规则

- 管理员在“设置 -> 自动化”中开启全局自动轮询，并设置 `3` 到 `86400` 秒的间隔。
- 每个分组的“自动轮询组内邮箱”开关决定定时任务是否读取该分组。未分组邮箱默认参与轮询。
- 用户在邮箱详情中主动刷新时不受分组自动轮询开关影响。
- 只有首次写入数据库的新邮件会触发投递；重复抓取同一邮件不会重复发送。
- 分组或邮箱的“通知与转发”开关关闭后，浏览器通知、SMTP、Telegram、Webhook 和 Shell 均不会发送。
- 投递失败会记录到 SQLite outbox，并在后续轮询中重试，最多尝试 3 次。

浏览器通知通过页面中的新邮件 feed 每 30 秒检查一次，因此需要 HX-Email 页面保持打开。它不是浏览器关闭后仍可送达的 VAPID Push。

## Webhook

启用 Webhook 后，HX-Email 向配置的 URL 发送 `POST` 请求：

```http
Content-Type: application/json
Authorization: Bearer <configured-token>
```

未配置 Token 时不发送 `Authorization`。成功响应必须是任意 `2xx` 状态码。事件结构如下：

```json
{
  "event": "new_mail",
  "message_id": 42,
  "user_id": 1,
  "usable_email": {
    "id": 7,
    "address": "inbox@example.com",
    "group_id": 3,
    "group_name": "registrations"
  },
  "message": {
    "from": "sender@example.net",
    "to": "inbox@example.com",
    "subject": "Your verification code",
    "body": "Code: 482913",
    "received_at": "2026-08-01T10:00:00Z",
    "verification_code": "482913"
  }
}
```

`group_id` 和 `verification_code` 在没有对应值时为 `null`，`group_name` 可以为空字符串。

## Shell 流水线

脚本路径必须指向后端运行环境中存在的 `.sh` 文件。HX-Email 使用下面的方式执行：

```text
/bin/sh /absolute/path/to/pipeline.sh
```

- 工作目录为脚本所在目录。
- stdin 是与 Webhook 相同的单个 JSON 事件。
- `HX_EMAIL_EVENT` 环境变量为 `new_mail`；测试按钮执行时为 `test`。
- `PATH` 和 `LANG` 会传入，其他进程环境变量不会继承。
- 超时范围为 1 到 300 秒。
- 退出码 `0` 表示成功；非零退出码、超时或脚本不存在都会记录为投递失败。
- stdout 仅用于设置页测试结果，最多保留 1000 个字符。

示例：

```sh
#!/bin/sh
payload=$(cat)
curl --fail --silent --show-error \
  -H 'Content-Type: application/json' \
  --data "$payload" \
  https://pipeline.example.com/new-mail
```

## 外部邮箱池 API

在“设置 -> API 安全”生成 Key 并开启外部邮箱池后，请求携带：

```http
Authorization: Bearer <generated-key>
```

可用端点：

- `POST /api/external/pool/claim-random`
- `POST /api/external/pool/claim-release`
- `POST /api/external/pool/claim-complete`
- `GET /api/external/pool/stats`

Key 轮换会立即使旧的主 Key 失效；“额外 API Keys”数组中的 Key 不受主 Key 轮换影响。
