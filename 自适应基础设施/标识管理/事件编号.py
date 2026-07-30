"""生成不影响交易随机状态的确定性编号。"""

import hashlib


def 生成编号(编号类型, *parts):
    text = "|".join([str(编号类型)] + [str(part) for part in parts])
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]
    return "%s-%s" % (编号类型, digest)

