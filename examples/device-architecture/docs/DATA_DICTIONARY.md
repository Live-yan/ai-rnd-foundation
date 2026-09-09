# 数据字典

仅描述本次生成的 biz_ 业务表；不声称是线上数据库反射，也不包含上游管理表。

## biz_device / 设备

|字段|类型|必填|引用|
|---|---|---|---|
|id|integer 主键|是|-|
|owner_id|string(80)，服务端从登录身份写入|是|-|
|created_at|timestamp，数据库默认时间|是|-|
|name|string|是|-|
|code|string|是|-|
|enabled|boolean|是|-|

## biz_maintenance / 检修记录

|字段|类型|必填|引用|
|---|---|---|---|
|id|integer 主键|是|-|
|owner_id|string(80)，服务端从登录身份写入|是|-|
|created_at|timestamp，数据库默认时间|是|-|
|device_id|reference|是|device|
|performed_on|date|是|-|
|notes|text|是|-|
