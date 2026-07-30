"""组合审批模式和安全切换规则。"""


允许的审批模式 = ("旧审批", "Shadow", "静态Active")


def 校验审批模式(mode):
    mode = str(mode or "旧审批")
    if mode not in 允许的审批模式:
        raise ValueError("审批模式必须是：旧审批、Shadow或静态Active")
    if mode == "静态Active":
        raise RuntimeError("静态Active尚未接入事件拆分，已安全拒绝启动")
    return mode

