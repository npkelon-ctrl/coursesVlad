"""Список адресов ИИ-сервисов для режима «VPN только для ИИ».

Бот спрашивает адреса у DNS сервера (10.8.0.1) — тем же, которым потом пользуется
устройство, поэтому маршруты и ответы DNS совпадают. Добавить сервис — дописать домен.
"""
import ipaddress

import dns.resolver

DNS_SERVER = "10.8.0.1"

DOMAINS = [
    # Claude / Anthropic
    "claude.ai", "www.claude.ai", "claude.com", "api.anthropic.com", "anthropic.com",
    "console.anthropic.com", "platform.claude.com", "code.claude.com", "statsig.anthropic.com",
    # OpenAI / ChatGPT
    "chatgpt.com", "www.chatgpt.com", "chat.openai.com", "openai.com", "www.openai.com",
    "api.openai.com", "auth.openai.com", "platform.openai.com", "cdn.openai.com",
    "cdn.oaistatic.com", "files.oaiusercontent.com", "sora.com",
    # Gemini / Google AI
    "gemini.google.com", "aistudio.google.com", "ai.google.dev", "makersuite.google.com",
    "generativelanguage.googleapis.com", "notebooklm.google.com",
    "alkalimakersuite-pa.clients6.google.com", "accounts.google.com", "www.google.com",
    "apis.google.com", "www.gstatic.com", "ssl.gstatic.com", "fonts.gstatic.com",
    "lh3.googleusercontent.com", "play.google.com",
]
# Сети, которые точно принадлежат сервисам
STATIC = ["160.79.104.0/23"]  # Anthropic


def ai_networks(rounds=3):
    r = dns.resolver.Resolver(configure=False)
    r.nameservers = [DNS_SERVER]
    r.lifetime = 5
    nets = {ipaddress.ip_network(n) for n in STATIC}
    for domain in DOMAINS:
        for _ in range(rounds):  # адреса у CDN меняются — спрашиваем несколько раз
            try:
                for a in r.resolve(domain, "A"):
                    # берём всю /24: соседние адреса того же пула CDN
                    nets.add(ipaddress.ip_network(f"{a.to_text()}/24", strict=False))
            except Exception:
                break
    return [str(n) for n in ipaddress.collapse_addresses(sorted(nets))]
