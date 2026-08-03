"""Deflated Sharpe Ratio — Bailey & López de Prado (CR-001/CR-1).

Neden gerekli: yeterince çok konfigürasyon denenirse, hiçbir gerçek avantajı olmayan
bir strateji bile yüksek Sharpe üretir. DSR, "kaç deneme yapıldığı" bilgisini kullanarak
gözlenen Sharpe'ı şans beklentisine göre düzeltir.

Kritik nokta (CR-002 P0-2): denenen konfigürasyon sayısı N **elle girilmez**, Experiment
Registry'den okunur — yalnız hyperopt denemeleri değil, o strateji ailesinin registry'ye
düşmüş TÜM koşuları. Bu sayı elle verilirse sistem kendi kendini kandırır.

Formüller:
    SR0  = sqrt(V) · [ (1−γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e)) ]
    DSR  = Φ[ (SR − SR0)·sqrt(T−1) / sqrt(1 − γ3·SR + (γ4−1)/4·SR²) ]
γ: Euler–Mascheroni sabiti · V: denemeler arası Sharpe varyansı · T: gözlem sayısı
γ3/γ4: getiri dağılımının çarpıklık/basıklığı.
"""

import math
from statistics import NormalDist

EULER_MASCHERONI = 0.5772156649015329
_ND = NormalDist()


def expected_max_sharpe(*, n_trials: int, sr_variance: float) -> float:
    """N deneme altında ŞANSLA beklenen en yüksek Sharpe (SR0)."""
    if n_trials < 2:
        raise ValueError(
            f"n_trials ≥ 2 olmalı (gelen: {n_trials}); tek denemede çoklu-deneme "
            "düzeltmesi tanımsızdır"
        )
    if sr_variance < 0:
        raise ValueError(f"sr_variance negatif olamaz: {sr_variance}")
    if sr_variance == 0:
        return 0.0
    a = _ND.inv_cdf(1 - 1 / n_trials)
    b = _ND.inv_cdf(1 - 1 / (n_trials * math.e))
    return math.sqrt(sr_variance) * ((1 - EULER_MASCHERONI) * a + EULER_MASCHERONI * b)


def deflated_sharpe(
    *,
    observed_sharpe: float,
    n_trials: int,
    sr_variance: float,
    n_observations: int,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """DSR: gözlenen Sharpe'ın şans olmama olasılığı [0,1]."""
    if n_observations < 2:
        raise ValueError(f"n_observations ≥ 2 olmalı (gelen: {n_observations})")
    sr0 = expected_max_sharpe(n_trials=n_trials, sr_variance=sr_variance)
    variance_term = 1 - skew * observed_sharpe + ((kurtosis - 1) / 4) * observed_sharpe**2
    if variance_term <= 0:
        raise ValueError(
            f"payda tanımsız (varyans terimi {variance_term:.4f} ≤ 0); "
            "çarpıklık/basıklık girdilerini kontrol et"
        )
    z = (observed_sharpe - sr0) * math.sqrt(n_observations - 1) / math.sqrt(variance_term)
    return _ND.cdf(z)


def verdict(dsr_value: float, *, alpha: float = 0.95) -> str:
    """CR-1: düzeltme sonrası anlamlılık yoksa strateji 'şans' etiketiyle reddedilir."""
    return "anlamli" if dsr_value >= alpha else "sans"
