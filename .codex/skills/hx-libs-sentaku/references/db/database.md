# 数据库与驱动库

## 数据库选择

| 优先级   | 数据库           | 规则                                               | 官方来源                      |
| -------- | ---------------- | -------------------------------------------------- | ----------------------------- |
| 1        | 用户指定的数据库 | 用户明确要求时优先满足，但 MySQL 除外              | -                             |
| 2        | SQLite / sqlite3 | 默认选择                                           | <https://sqlite.org/>         |
| 3        | PostgreSQL       | 用户需要服务端数据库、多实例或更强数据库能力时选择 | <https://www.postgresql.org/> |
| 禁用推荐 | MySQL            | 任何时候不主动推荐                                 | <https://www.mysql.com/>      |

## Python 驱动/访问库

| 数据库           | 默认库                  | 备注                                 | 官方来源                                         |
| ---------------- | ----------------------- | ------------------------------------ | ------------------------------------------------ |
| SQLite           | Python 标准库 `sqlite3` | 默认优先                             | <https://docs.python.org/3/library/sqlite3.html> |
| SQLite async     | aiosqlite               | 只有 async SQLite 访问确有需要时使用 | <https://aiosqlite.omnilib.dev/>                 |
| PostgreSQL       | Psycopg 3               | PostgreSQL 默认 Python driver        | <https://www.psycopg.org/psycopg3/docs/>         |
| PostgreSQL async | asyncpg                 | 只有项目明确采用 async DB 访问时使用 | <https://magicstack.github.io/asyncpg/current/>  |
| ORM              | SQLAlchemy              | 需要统一 ORM/SQL 表达式时使用        | <https://docs.sqlalchemy.org/>                   |

## MySQL 规则

- 不推荐 MySQL。
- 不把 MySQL 写进“可选方案”。
- 用户强制要求 MySQL 时，只说明这是用户硬约束，不作为本技能推荐。
