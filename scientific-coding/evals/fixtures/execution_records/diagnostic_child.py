"""
输出已有诊断程序的连续消息，供运行边界完整收集。

命令行 TOKEN --> 子进程 stdout + stderr
"""

# 此文件属于已有外部接口，评测任务要求保持字节不变。
import sys

token = sys.argv[1]
for number in range(24):
    print(f"CHILD_STDOUT:{token}:{number}", flush=True)
    print(f"CHILD_STDERR:{token}:{number}", file=sys.stderr, flush=True)
