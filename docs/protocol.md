# TCP 仪器协议 v1

这是本项目的自定义演示协议，使用 SCPI 风格命令名。它并非某品牌的完整 SCPI 实现，不能直接套用到未知仪器。

## 传输层

- TCP，默认 `127.0.0.1:5025`；客户端读/写超时 2 秒。
- 客户端发送 ASCII 命令，以 LF (`\n`) 结束。
- 服务端按一问一答返回 UTF-8 文本，以 LF 结束。
- 客户端按行读取，能处理一次响应被 TCP 拆成多个包的情况，不假设一次 `recv` 就是一帧。
- 客户端单响应最大 1 MiB；无完整换行、点数错误、非数字、布尔值、NaN/Infinity 均视为错误，结束本次采集。
- 当前仅支持 IPv4/主机名的 `host:port` 界面格式，没有 TLS 或身份认证。

## 命令

| 请求 | 响应示例 | 说明 |
| --- | --- | --- |
| `*IDN?` | `InstrumentLab, Virtual DAQ, SIM-001, 1.0` | 设备标识 |
| `ACQ:CONF?` | `{"sample_rate":1024,"block_size":256,...}` | 至少包含采样率和块长 |
| `MEAS:WAV?` | `[0.012,0.604,...]` | 恰好 256 个原始电压值，单位 V |

配置查询使用 JSON 对象，波形查询使用 JSON 数组。省略号仅用于文档示意，真实响应是完整 JSON。仿真服务端的未知命令返回 `ERROR: unsupported command`。

## 连接顺序

```text
connect(host, port)
    *IDN?        → identity
    ACQ:CONF?    → 校验 sample_rate 和 block_size
loop:
    MEAS:WAV?    → 校验 JSON、长度、数值类型和有限性
    采集与保存
close
```

采样率不匹配时拒绝采集，避免时间轴和频率轴出错。仿真服务端每个 TCP 连接有独立样点索引，重新连接后时间从 0 开始。客户端按每块对应时长调度查询，服务端不模拟 ADC 缓冲区和硬件采样时钟。

## 接入真实硬件

保留驱动的 `connect() -> str`、`read_block() -> (start_seconds, raw_voltage_list)`、`close()` 三个接口，在新驱动内完成该设备的配置命令、响应解析、单位换算和错误检查。

真实仪器可能返回 IEEE 二进制块、整数 ADC 码、波形前导码或另一套命令。接入时需要依据具体设备手册实现，不应仅更换 IP 地址就宣称支持。当前项目未包含串口、Modbus 和 VISA 驱动，也未提供设备输出控制或量程切换。
