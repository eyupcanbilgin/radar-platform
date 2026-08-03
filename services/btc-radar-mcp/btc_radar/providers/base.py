"""Tüm veri kaynağı provider'larının ortak sözleşmesi.

Somut provider dosyalarının başına şu yorum bloğu zorunludur (CLAUDE.md):
kaynak URL, rate limit, bilinen tuhaflıklar — gelecekteki geliştiriciye ders bırak.
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from btc_radar.models.observation import RawObservation


class BaseProvider(ABC):
    """Kaynak başına bir provider; çıkış her zaman doğrulanmış RawObservation listesidir.

    Pydantic doğrulaması yalnızca burada (provider çıkışında) yapılır; router ham dict taşır
    ve sıcak yolda tekrar doğrulama yoktur (SPEC §3.2 madde 2).
    """

    name: ClassVar[str]
    source_group: ClassVar[str]

    @abstractmethod
    async def fetch(self, metric: str, **params: Any) -> list[RawObservation]:
        """Metrik için ham gözlemleri getir.

        Parse edilemeyen sayı ValueError fırlatır; sessizce 0/None'a düşülmez
        (fail-loud, CLAUDE.md kural 2).
        """
