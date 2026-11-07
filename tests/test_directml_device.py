from hpg_core.ai_models import directml_device


def _adapter(index, name, gib, vendor=0x1002, flags=0):
    return {"index": index, "name": name,
            "dedicated_video": int(gib * 1024 ** 3),
            "vendor": vendor, "device": index, "flags": flags}


def test_prefers_rx_7800_xt_over_integrated_adapter():
    adapters = [_adapter(0, "AMD Radeon(TM) Graphics", .5),
                _adapter(1, "AMD Radeon RX 7800 XT", 16)]
    assert directml_device.choose_device_id(adapters) == 1


def test_uses_largest_discrete_adapter_and_rejects_software():
    adapters = [_adapter(0, "Integrated", .5),
                _adapter(1, "Discrete A", 4),
                _adapter(2, "Discrete B", 8),
                _adapter(3, "Basic Render Driver", 16, vendor=0x1414, flags=2)]
    assert directml_device.choose_device_id(adapters) == 2


def test_no_discrete_adapter_uses_cpu():
    assert directml_device.choose_device_id([_adapter(0, "Integrated", .5)]) is None


def test_integrated_gpu_with_reserved_vram_uses_cpu():
    adapters = [_adapter(0, "AMD Radeon(TM) Graphics", 2)]
    assert directml_device.choose_device_id(adapters) is None
