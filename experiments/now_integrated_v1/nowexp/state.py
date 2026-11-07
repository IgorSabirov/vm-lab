from dataclasses import dataclass, field, asdict
import math


@dataclass
class Apparatus:
    identity: str
    made_by: str
    generation: int
    template: int
    material_units: int = 1


@dataclass
class Cell:
    identity: str
    generation: int
    fuel: int = 0
    precursor: int = 0
    fuel_capacity: int = 16
    precursor_capacity: int = 8
    reserved_fuel: int = 0
    reserved_precursor: int = 0
    apparatus: list = field(default_factory=list)
    pending: dict = field(default_factory=dict)
    memories: dict = field(default_factory=dict)
    decoded: dict = field(default_factory=dict)
    contact: bool = False
    contact_origin: str = "absent"
    address: str | None = None
    active: bool = False
    started_at: float | None = None
    health: int = 7
    transmitted: bool = False
    material_waste: int = 0
    spent_fuel: int = 0
    unavailable_fuel: int = 0
    unavailable_material: int = 0
    contact_material: int = 0
    costs: dict = field(default_factory=dict)
    failures: list = field(default_factory=list)
    last_read_quality: dict = field(default_factory=dict)

    def pay(self, n, purpose):
        if n < 0:
            raise ValueError("negative debit")
        if self.fuel < n:
            self.failures.append("fuel:" + purpose)
            return False
        self.fuel -= n
        self.spent_fuel += n
        self.costs[purpose] = self.costs.get(purpose, 0) + n
        return True

    def local_view(self):
        """Controller receives this local state, not other cells or global log."""
        return dict(identity=self.identity, generation=self.generation,
                    fuel=self.fuel, precursor=self.precursor,
                    decoded=dict(self.decoded), apparatus=list(self.apparatus),
                    contact=self.contact, address=self.address, health=self.health)

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Config:
    generations: int = 3
    production: bool = True
    repair_contacts: bool = True
    corrector: bool = True
    initial_seed: bool = True
    retire_inherited: bool = True
    transfer_apparatus: bool = True
    reader_enabled: bool = True
    address_enabled: bool = True
    imported_contacts: bool = False
    erase_record: bool = False
    source_repeat: bool = False
    memory: str = "classical"
    detuning: float = 0.0
    bath_modes: int = 8
    bath_coupling: float = 0.35
    classical_survival: float = 1.0
    supply_delay: float = 0.0
    record_delay: float = 0.0
    donor_fuel: int = 48
    donor_precursor: int = 16
    receiver_velocity: float = 0.0
    read_wait: float = 32.0
    forced_content: tuple | None = None
    preparation: str = "correlated"
    scramble_child: bool = False
    scheduler_reverse: bool = False
    working_slots: int = 2
    max_events: int = 1000

    def validate(self):
        for name in ("generations", "bath_modes", "donor_fuel", "donor_precursor", "working_slots", "max_events"):
            if type(getattr(self, name)) is not int:
                raise ValueError("integer resource/count required: " + name)
        for name in ("detuning", "bath_coupling", "classical_survival", "supply_delay", "record_delay", "receiver_velocity", "read_wait"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError("nonfinite parameter: " + name)
        if self.bath_coupling < 0:
            raise ValueError("negative coupling")
        if self.forced_content is not None and (len(self.forced_content) != 2 or any(x not in (0,1) for x in self.forced_content)):
            raise ValueError("content requires two classical bits")
        if not 1 <= self.generations <= 8:
            raise ValueError("generations outside reviewed envelope")
        if self.memory not in ("classical", "finite_dark", "finite_static"):
            raise ValueError("unknown memory backend")
        if self.preparation not in ("correlated", "independent"):
            raise ValueError("unknown preparation law")
        if not 2 <= self.bath_modes <= 64:
            raise ValueError("bath size outside envelope")
        if not 0 <= self.classical_survival <= 1 or abs(self.receiver_velocity) >= 0.5:
            raise ValueError("invalid probability or material carrier cannot catch worldline")
        if min(self.donor_fuel, self.donor_precursor, self.supply_delay, self.record_delay) < 0:
            raise ValueError("negative stock or delay")
        if self.working_slots < 0 or self.read_wait < 1 or self.max_events < 1:
            raise ValueError("invalid finite budget")
        return self
