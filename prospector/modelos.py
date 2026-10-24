import dataclasses
from dataclasses import dataclass, field


@dataclass
class Municipio:
    ibge: str          # "2304400"
    nome: str          # "Fortaleza"
    uf: str            # "CE"
    lat: float
    lng: float
    populacao: int = 0


@dataclass
class Lead:
    id: str                    # "osm:node/123" | "cnpj:12345678000190"
    fonte: str                 # "OSM" | "Receita" | "OSM+Receita"
    nome: str
    tipo: str                  # chave de config.PESO_TIPO
    municipio_ibge: str
    cidade: str
    uf: str
    lat: float
    lng: float
    tags: dict = field(default_factory=dict)   # tags OSM; {} ou sintéticas p/ Receita
    site: str = ""
    redes: str = ""
    telefone: str = ""         # E.164: "+5585999998888"
    whatsapp: str = ""         # "https://wa.me/5585999998888"
    email: str = ""
    cnpj: str = ""             # 14 dígitos
    abertura: str = ""         # "AAAA-MM-DD"
    status_site: str = ""      # "Sem site" | "Só rede social" | "A verificar" | "Tem site"
                               # | "Site fora do ar" | "Não conferido"

    def tem_contato(self) -> bool:
        """Verifica se o lead possui ao menos um canal de contato."""
        return bool(self.telefone or self.email or self.redes or self.whatsapp)

    def para_dict(self) -> dict:
        """Converte o lead em dicionário serializável."""
        return dataclasses.asdict(self)

    @classmethod
    def de_dict(cls, d: dict) -> "Lead":
        """Reconstrói um Lead a partir de um dicionário, ignorando chaves desconhecidas."""
        campos_validos = {f.name for f in dataclasses.fields(cls)}
        dados = {k: v for k, v in (d or {}).items() if k in campos_validos}
        return cls(**dados)


@dataclass
class Estab:
    cnpj: str
    nome: str
    cnae: str
    tipo: str
    municipio_ibge: str
    uf: str
    logradouro: str
    bairro: str
    cep: str
    telefone: str
    telefone2: str
    email: str
    abertura: str
