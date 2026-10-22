"""Работа с WireGuard: ключи, адреса, добавление и удаление устройств."""
import ipaddress
import json
import re
import subprocess
from pathlib import Path

IFACE = "wg0"
CONF = Path("/etc/wireguard/wg0.conf")
SERVER_PUB = Path("/etc/wireguard/server.pub")
NET = ipaddress.ip_network("10.8.0.0/24")


def _run(*cmd, inp=None):
    return subprocess.run(cmd, input=inp, capture_output=True, text=True, check=True).stdout.strip()


class Devices:
    def __init__(self, db_path, endpoint, max_devices):
        self.db = Path(db_path)
        self.endpoint = endpoint
        self.max = max_devices
        self.db.parent.mkdir(parents=True, exist_ok=True)

    def _load(self):
        return json.loads(self.db.read_text("utf-8")) if self.db.exists() else []

    def _save(self, items):
        self.db.write_text(json.dumps(items, ensure_ascii=False, indent=2), "utf-8")

    def list(self):
        return self._load()

    def _free_ip(self, items):
        used = {d["ip"] for d in items}
        for host in list(NET.hosts())[1:]:  # .1 занят сервером
            if str(host) not in used:
                return str(host)
        raise RuntimeError("Нет свободных адресов")

    def add(self, name, ai_only=False):
        items = self._load()
        if len(items) >= self.max:
            raise ValueError(f"Уже {self.max} устройств — сначала удали ненужное")
        name = re.sub(r"[^\w .-]", "", name)[:30] or "device"
        priv = _run("wg", "genkey")
        pub = _run("wg", "pubkey", inp=priv)
        psk = _run("wg", "genpsk")
        ip = self._free_ip(items)
        # в живой интерфейс (без перезапуска) и в файл (чтобы пережило перезагрузку)
        _run("wg", "set", IFACE, "peer", pub, "preshared-key", "/dev/stdin", "allowed-ips", f"{ip}/32", inp=psk)
        with CONF.open("a") as f:
            f.write(f"\n# {name}\n[Peer]\nPublicKey = {pub}\nPresharedKey = {psk}\nAllowedIPs = {ip}/32\n")
        items.append({"name": name, "ip": ip, "pub": pub, "ai_only": ai_only})
        self._save(items)
        if ai_only:
            from routes import ai_networks
            # DNS сервера (10.8.0.1) + только адреса ИИ-сервисов; остальное идёт напрямую
            allowed = ", ".join(["10.8.0.1/32"] + ai_networks())
            dns = "10.8.0.1"
        else:
            allowed, dns = "0.0.0.0/0, ::/0", "1.1.1.1, 8.8.8.8"
        conf = (
            "[Interface]\n"
            f"PrivateKey = {priv}\n"
            f"Address = {ip}/32\n"
            f"DNS = {dns}\n\n"
            "[Peer]\n"
            f"PublicKey = {SERVER_PUB.read_text().strip()}\n"
            f"PresharedKey = {psk}\n"
            f"Endpoint = {self.endpoint}\n"
            f"AllowedIPs = {allowed}\n"
            "PersistentKeepalive = 25\n"
        )
        return name, ip, conf

    def remove(self, pub):
        items = self._load()
        if not any(d["pub"] == pub for d in items):
            return False
        _run("wg", "set", IFACE, "peer", pub, "remove")
        text = CONF.read_text()
        blocks = re.split(r"(?=\n# [^\n]*\n\[Peer\])", text)
        CONF.write_text("".join(b for b in blocks if pub not in b))
        self._save([d for d in items if d["pub"] != pub])
        return True
