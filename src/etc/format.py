import copy
import uuid


def maybe_cast_to_str(d: dict, uuid_to_str: bool = False):
    ans = copy.deepcopy(d)
    for k, v in d.items():
        if (
            isinstance(k, str)
            and (k.endswith("id"))
            and uuid_to_str
            and isinstance(v, uuid.UUID)
        ):
            ans[k] = str(v)
        elif isinstance(v, dict):
            ans[k] = maybe_cast_to_str(v, uuid_to_str=uuid_to_str)
        elif isinstance(v, list):
            ans[k] = [str(x) for x in v]
    return ans
