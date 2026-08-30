"""
Body Composition Calculation Engine for Cult Smart Scale.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"


class BodyType(str, Enum):
    THIN = "Thin"
    LACK_EXERCISE = "Lack of Exercise"
    OBESE_FAT = "Obese / High Fat"
    THIN_MUSCLE = "Thin Muscle"
    STANDARD = "Standard"
    FAT_MUSCLE = "Fat Muscle"
    MUSCULAR = "Muscular"
    STANDARD_MUSCLE = "Standard Muscle"
    MUSCLE_FAT = "Muscle Fat"


@dataclass
class UserProfile:
    user_id: str
    name: str
    person_entity: Optional[str] = None
    height_cm: float = 175.0
    age: int = 28
    gender: Gender = Gender.MALE
    is_athlete: bool = False
    target_weight: float = 75.0
    weight_tolerance: float = 3.5
    target_impedance: Optional[int] = None
    impedance_tolerance: int = 60


@dataclass
class ScaleReading:
    weight_kg: float
    is_stabilized: bool
    impedance_raw: int = 0
    impedance_ohms: int = 0
    heart_rate_bpm: Optional[int] = None
    battery_level: Optional[int] = None
    body_metrics: Optional[Dict[str, Any]] = None
    raw_hex: str = ""
    is_finalized: bool = False


def verify_checksum(packet: bytes) -> bool:
    """Verifies XOR checksum on an 11-byte scale packet."""
    if len(packet) != 11:
        return False
    chk = 0
    for b in packet[:10]:
        chk ^= b
    return chk == packet[10]


def decode_impedance(enc: int) -> int:
    """
    Decodes 24-bit encoded bioimpedance to resistance in Ohms.
    """
    if enc in (0, 0xFFFFFF):
        return 0
    w8 = (enc >> 12) & 0x0F
    w9 = (enc & 0x0F00) | ((enc >> 16) & 0xFF)
    w10 = (enc & 0xFF) << 2
    diff = w9 - (w10 + w8)
    if diff < 0:
        diff += 1
    ohms = diff >> 1
    return ohms


def calculate_body_composition(
    weight_kg: float,
    impedance_ohms: int = 0,
    profile: Optional[UserProfile] = None,
    user: Optional[UserProfile] = None,
) -> Dict[str, Any]:
    """
    Computes full body composition parameters for Cult Smart Scale.
    """
    p = profile or user
    if p is None:
        raise ValueError("A UserProfile (profile or user) must be provided")

    height_m = p.height_cm / 100.0
    bmi = weight_kg / (height_m ** 2)
    age = p.age
    sex = 0 if (isinstance(p.gender, Gender) and p.gender == Gender.MALE) or str(p.gender).lower() == "male" else 1
    ath = 1 if p.is_athlete else 0
    variant = (sex << 1) | ath  # 0: M normal, 1: M ath, 2: F normal, 3: F ath

    # 1. Body Fat %
    if variant == 0:
        fat_rate = 1.545 * bmi + 0.0979 * age - 13.74
    elif variant == 1:
        fat_rate = 1.488 * bmi + 0.0886 * age - 15.69
    elif variant == 2:
        fat_rate = 1.393 * bmi + 0.0827 * age - 4.414
    else:
        fat_rate = 1.341 * bmi + 0.0768 * age - 6.364
    fat_rate = max(5.1, min(70.0, fat_rate))
    fat_mass_kg = weight_kg * (fat_rate / 100.0)
    fat_free_mass_kg = weight_kg - fat_mass_kg

    # 2. Muscle Mass (kg) & Rate (%)
    if variant == 0:
        mus_coeff = -0.01452 * bmi + 1.069 - 0.000922 * age
        mus_coeff = max(0.282, min(0.893, mus_coeff))
    elif variant == 1:
        mus_coeff = -0.01447 * bmi + 1.167 - 0.000955 * age
        mus_coeff = max(0.285, min(0.9015, mus_coeff))
    elif variant == 2:
        mus_coeff = -0.008751 * bmi + 0.9828 - 0.000308 * age
        mus_coeff = max(0.282, min(0.893, mus_coeff))
    else:
        mus_coeff = -0.007303 * bmi + 1.012 - 0.000273 * age
        mus_coeff = max(0.285, min(0.9015, mus_coeff))
    muscle_kg = weight_kg * mus_coeff
    muscle_rate = (muscle_kg / weight_kg) * 100.0

    # 3. Total Body Water (%) & Mass (kg)
    if variant == 0:
        water_rate = -0.06742 * age + 78.04 - 0.900 * bmi
        water_rate = max(20.6, min(65.1, water_rate))
    elif variant == 1:
        water_rate = -0.07259 * age + 88.72 - 1.100 * bmi
        water_rate = max(21.7, min(68.5, water_rate))
    elif variant == 2:
        water_rate = -0.02273 * age + 71.78 - 0.6393 * bmi
        water_rate = max(20.6, min(65.1, water_rate))
    else:
        water_rate = -0.02068 * age + 76.92 - 0.5551 * bmi
        water_rate = max(21.7, min(68.5, water_rate))
    water_kg = weight_kg * (water_rate / 100.0)

    # 4. Bone Mass (kg)
    if variant == 0:
        bone_coeff = max(0.10, min(0.40, -0.0005467 * bmi + 0.4026 - 0.000347 * age)) * 0.1695
    elif variant == 1:
        bone_coeff = max(0.05, min(0.40, -0.0004495 * bmi + 0.3626 - 0.000297 * age)) * 0.1695
    elif variant == 2:
        bone_coeff = max(0.10, min(0.40, -0.0003299 * bmi + 0.3703 - 0.000116 * age)) * 0.1695
    else:
        bone_coeff = max(0.05, min(0.40, -0.0002267 * bmi + 0.3143 - 0.000085 * age)) * 0.1695
    bone_kg = max(1.0, weight_kg * bone_coeff)

    # 5. Basal Metabolic Rate (BMR kcal/day)
    if sex == 0:
        bmr = int(10 * weight_kg + 6.25 * p.height_cm - 5 * age + 5)
    else:
        bmr = int(10 * weight_kg + 6.25 * p.height_cm - 5 * age - 161)

    # 6. Visceral Fat Level (1..30)
    vfal = int(0.1 * bmi * (age / 35.0) * (fat_rate / 20.0) + 1)
    vfal = max(1, min(30, vfal))

    # 7. Protein (%) & Mass (kg)
    if variant == 0:
        protein_rate = -0.04691 * bmi + 29.55 - 0.02979 * age
    elif variant == 2:
        protein_rate = -0.02831 * bmi + 26.78 - 0.01007 * age
    else:
        protein_rate = -0.03477 * bmi + 28.03 - 0.02299 * age
    protein_rate = max(5.0, min(24.0, protein_rate))
    protein_kg = weight_kg * (protein_rate / 100.0)

    # 8. Subcutaneous Fat (%)
    subcut_rate = max(4.7, min(61.0, fat_rate * 0.88))

    # 9. Skeletal Muscle (kg)
    skeletal_kg = muscle_kg * 0.72

    # 10. Ideal Weight & Body Type
    ideal_weight = (height_m ** 2) * 21.75
    if bmi <= 18.5:
        btype = BodyType.THIN if fat_rate <= 10.0 else (BodyType.LACK_EXERCISE if fat_rate <= 21.0 else BodyType.OBESE_FAT)
    elif bmi <= 24.0:
        btype = BodyType.THIN_MUSCLE if fat_rate <= 10.0 else (BodyType.STANDARD if fat_rate <= 21.0 else BodyType.FAT_MUSCLE)
    else:
        btype = BodyType.MUSCULAR if fat_rate <= 10.0 else (BodyType.STANDARD_MUSCLE if fat_rate <= 21.0 else BodyType.MUSCLE_FAT)

    # 11. Body Age estimate
    diff_fat = fat_rate - (20.0 if sex == 0 else 25.0)
    body_age = max(18, min(80, int(age + diff_fat * 0.5)))

    return {
        "weight_kg": round(weight_kg, 2),
        "bmi": round(bmi, 2),
        "body_fat_percentage": round(fat_rate, 1),
        "body_fat_kg": round(fat_mass_kg, 2),
        "fat_free_mass_kg": round(fat_free_mass_kg, 2),
        "muscle_mass_kg": round(muscle_kg, 2),
        "muscle_percentage": round(muscle_rate, 1),
        "skeletal_muscle_kg": round(skeletal_kg, 2),
        "water_percentage": round(water_rate, 1),
        "water_kg": round(water_kg, 2),
        "bone_mass_kg": round(bone_kg, 2),
        "protein_percentage": round(protein_rate, 1),
        "protein_kg": round(protein_kg, 2),
        "subcutaneous_fat_percentage": round(subcut_rate, 1),
        "visceral_fat_level": vfal,
        "bmr_kcal": bmr,
        "body_age": body_age,
        "ideal_weight_kg": round(ideal_weight, 2),
        "body_type": btype.value,
        "impedance_ohms": impedance_ohms,
    }
