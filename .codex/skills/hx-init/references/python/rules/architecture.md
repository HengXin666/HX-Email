# 架构规则 (按需加载)

## 深模块 vs 浅模块

- 浅模块: 10个30行小文件, Agent 要跳读10处。
- 深模块: 1个清爽接口 + impl/ 复杂实现, Agent 读1处即可用。

## 门面 (**init**.py) 示例

    from server.user.login import login_user
    __all__ = ["login_user"]

调用方: from server.user import login_user, 无需知道内部结构。

## impl 边界

    server/user/
      login.py            # 公开: 只能 import impl, 禁止 _func
      impl/login_impl.py  # 私有: 这里才能 _validate_pwd()

## 拆分触发

- 文件 >300 行 -> 私有逻辑下沉 impl/
- 目录 .py >5 -> 按子业务再分目录
- 目录 .py <2 -> 与相邻目录合并 (避免碎片化)
