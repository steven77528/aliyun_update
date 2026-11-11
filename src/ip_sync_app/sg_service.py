from __future__ import annotations

import time
from typing import Any, Callable, Tuple

from .models import AccountConfig, Target


class AliyunRuleUpdater:
    def __init__(self, account: AccountConfig):
        self.account = account

    def update_rule_source_cidr(self, target: Target, new_ip: str) -> Tuple[bool, str]:
        try:
            from aliyunsdkcore.client import AcsClient  # type: ignore
            from aliyunsdkecs.request.v20140526.ModifySecurityGroupRuleRequest import (  # type: ignore
                ModifySecurityGroupRuleRequest,
            )
        except Exception as e:
            return False, f"sdk_import_failed:{e}"

        request = ModifySecurityGroupRuleRequest()
        request.set_SecurityGroupRuleId(target.rule_identifier)
        request.set_SourceCidrIp(f"{new_ip}/32")
        request.set_SecurityGroupId(target.security_group_id)

        client = AcsClient(self.account.access_key_id, self.account.access_key_secret, self.account.region_id)
        try:
            _ = client.do_action_with_exception(request)
            return True, "ok"
        except Exception as e:
            return False, f"api_error:{e}"


class HuaweiRuleUpdater:
    def __init__(self, account: AccountConfig):
        self.account = account

    def _build_client(self) -> Any:
        try:
            from huaweicloudsdkcore.auth.credentials import BasicCredentials  # type: ignore
            from huaweicloudsdkvpc.v3 import VpcClient  # type: ignore
            from huaweicloudsdkvpc.v3.region.vpc_region import VpcRegion  # type: ignore
        except Exception as e:
            raise RuntimeError(f"sdk_import_failed:{e}") from e

        credentials = BasicCredentials(self.account.access_key_id, self.account.access_key_secret)
        return VpcClient.new_builder().with_credentials(credentials).with_region(VpcRegion.value_of(self.account.region_id)).build()

    def _extract_multiport(self, rule: Any) -> Any:
        multiport = getattr(rule, "multiport", None)
        if multiport:
            return str(multiport)

        port_min = getattr(rule, "port_range_min", None)
        port_max = getattr(rule, "port_range_max", None)
        if port_min is None and port_max is None:
            return None
        if port_min == port_max or port_max is None:
            return str(port_min)
        return f"{port_min}-{port_max}"

    def _build_rule_body(self, rule: Any, new_ip: str, security_group_id: str | None = None) -> Any:
        try:
            from huaweicloudsdkvpc.v3 import CreateSecurityGroupRuleOption, CreateSecurityGroupRuleRequestBody  # type: ignore
        except Exception as e:
            raise RuntimeError(f"sdk_import_failed:{e}") from e

        priority = getattr(rule, "priority", None)
        option_kwargs = {
            "security_group_id": getattr(rule, "security_group_id", None) or security_group_id,
            "direction": getattr(rule, "direction", None),
            "ethertype": getattr(rule, "ethertype", None),
            "protocol": getattr(rule, "protocol", None),
            "multiport": self._extract_multiport(rule),
            "remote_ip_prefix": f"{new_ip}/32",
            "description": getattr(rule, "description", None),
            "action": getattr(rule, "action", None),
            "enabled": getattr(rule, "enabled", None),
        }
        if priority is not None:
            option_kwargs["priority"] = str(priority)

        option = CreateSecurityGroupRuleOption(**{k: v for k, v in option_kwargs.items() if v is not None})
        return CreateSecurityGroupRuleRequestBody(security_group_rule=option)

    def _build_show_request(self, security_group_id: str) -> Any:
        from huaweicloudsdkvpc.v3 import ShowSecurityGroupRequest  # type: ignore

        return ShowSecurityGroupRequest(security_group_id=security_group_id)

    def _build_create_request(self, body: Any) -> Any:
        from huaweicloudsdkvpc.v3 import CreateSecurityGroupRuleRequest  # type: ignore

        return CreateSecurityGroupRuleRequest(body=body)

    def _build_delete_request(self, rule_identifier: str) -> Any:
        from huaweicloudsdkvpc.v3 import DeleteSecurityGroupRuleRequest  # type: ignore

        return DeleteSecurityGroupRuleRequest(security_group_rule_id=rule_identifier)

    def update_rule_source_cidr(self, target: Target, new_ip: str) -> Tuple[bool, str]:
        try:
            client = self._build_client()
        except Exception as e:
            return False, str(e)

        try:
            show_resp = client.show_security_group(self._build_show_request(target.security_group_id))
            security_group = getattr(show_resp, "security_group", None)
            rules = getattr(security_group, "security_group_rules", None) or []
            matched_rule = next((rule for rule in rules if getattr(rule, "id", None) == target.rule_identifier), None)
            if matched_rule is None:
                return False, f"rule_not_found:{target.rule_identifier}"
            if getattr(matched_rule, "remote_ip_prefix", None) == f"{new_ip}/32":
                return True, "ok"
            body = self._build_rule_body(matched_rule, new_ip, target.security_group_id)
            create_resp = client.create_security_group_rule(self._build_create_request(body))
            created_rule = getattr(create_resp, "security_group_rule", None)
            created_rule_id = getattr(created_rule, "id", None)
            client.delete_security_group_rule(self._build_delete_request(target.rule_identifier))
            if created_rule_id:
                target.rule_identifier = str(created_rule_id)
            return True, "ok"
        except Exception as e:
            return False, f"api_error:{e}"


class CloudRuleUpdater:
    def __init__(self, account: AccountConfig):
        self.account = account
        if account.provider == "aliyun":
            self._delegate: Any = AliyunRuleUpdater(account)
        elif account.provider == "huawei":
            self._delegate = HuaweiRuleUpdater(account)
        else:
            self._delegate = None

    def update_rule_source_cidr(self, target: Target, new_ip: str) -> Tuple[bool, str]:
        if self._delegate is None:
            return False, f"unsupported_provider:{self.account.provider}"
        return self._delegate.update_rule_source_cidr(target, new_ip)


def execute_update_with_retry(
    updater: Callable[[], Tuple[bool, str]],
    retry_count: int,
    retry_backoff_seconds: float,
) -> Tuple[bool, int, str]:
    last_error = ""
    for i in range(retry_count + 1):
        ok, msg = updater()
        if ok:
            return True, i + 1, "ok"
        last_error = msg
        if i < retry_count:
            time.sleep(retry_backoff_seconds * (2**i))
    return False, retry_count + 1, last_error
