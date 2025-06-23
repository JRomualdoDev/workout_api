from datetime import datetime
import re
from uuid import uuid4
from fastapi import APIRouter, Body, HTTPException, status
from pydantic import UUID4
import urllib.parse

from workout_api.atleta.schemas import AtletaIn, AtletaOut, AtletaUpdate
from workout_api.atleta.models import AtletaModel
from workout_api.categorias.models import CategoriaModel
from workout_api.centro_treinamento.models import CentroTreinamentoModel

from workout_api.contrib.dependencies import DatabaseDependency
from sqlalchemy.future import select

router = APIRouter()


@router.post(
    "/",
    summary="Criar um novo atleta",
    status_code=status.HTTP_201_CREATED,
    response_model=AtletaOut,
)
async def post(db_session: DatabaseDependency, atleta_in: AtletaIn = Body(...)):
    categoria_nome = atleta_in.categoria.nome
    centro_treinamento_nome = atleta_in.centro_treinamento.nome

    categoria = (
        (
            await db_session.execute(
                select(CategoriaModel).filter_by(nome=categoria_nome)
            )
        )
        .scalars()
        .first()
    )

    if not categoria:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A categoria {categoria_nome} não foi encontrada.",
        )

    centro_treinamento = (
        (
            await db_session.execute(
                select(CentroTreinamentoModel).filter_by(nome=centro_treinamento_nome)
            )
        )
        .scalars()
        .first()
    )

    if not centro_treinamento:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"O centro de treinamento {centro_treinamento_nome} não foi encontrado.",
        )
    try:
        atleta_out = AtletaOut(
            id=uuid4(), created_at=datetime.utcnow(), **atleta_in.model_dump()
        )
        atleta_model = AtletaModel(
            **atleta_out.model_dump(exclude={"categoria", "centro_treinamento"})
        )

        atleta_model.categoria_id = categoria.pk_id
        atleta_model.centro_treinamento_id = centro_treinamento.pk_id

        db_session.add(atleta_model)
        await db_session.commit()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro ao inserir os dados no banco",
        )

    return atleta_out


@router.get(
    "/",
    summary="Consultar todos os Atletas",
    status_code=status.HTTP_200_OK,
    response_model=list[AtletaOut],
)
async def query(db_session: DatabaseDependency) -> list[AtletaOut]:
    atletas: list[AtletaOut] = (
        (await db_session.execute(select(AtletaModel))).scalars().all()
    )

    return [AtletaOut.model_validate(atleta) for atleta in atletas]


@router.get(
    "/{id}",
    summary="Consulta um Atleta pelo id",
    status_code=status.HTTP_200_OK,
    response_model=AtletaOut,
)
async def get(id: UUID4, db_session: DatabaseDependency) -> AtletaOut:
    atleta: AtletaOut = (
        (await db_session.execute(select(AtletaModel).filter_by(id=id)))
        .scalars()
        .first()
    )

    if not atleta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Atleta não encontrado no id: {id}",
        )

    return atleta


@router.get(
    "/nome/{nome}",
    summary="Consulta um Atleta pelo nome",
    status_code=status.HTTP_200_OK,
    response_model=AtletaOut,
)
async def get(nome: str, db_session: DatabaseDependency) -> AtletaOut:

    # Decodificar URL encoding
    nome_decoded = urllib.parse.unquote(nome)

    atleta: AtletaOut = (
        (
            await db_session.execute(
                select(AtletaModel).filter(AtletaModel.nome.ilike(f"%{nome_decoded}%"))
            )
        )
        .scalars()
        .first()
    )

    if not atleta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Atleta não encontrado no nome: {nome}",
        )

    return atleta


@router.get(
    "/cpf/{cpf}",
    summary="Consulta um Atleta pelo cpf",
    status_code=status.HTTP_200_OK,
    response_model=AtletaOut,
)
async def get(cpf: str, db_session: DatabaseDependency) -> AtletaOut:
    # Limpa o CPF (remove formatação)
    cpf_limpo = limpar_cpf(cpf)

    # Valida o CPF
    if not validar_cpf(cpf_limpo):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"CPF inválido: {cpf}"
        )

    result = await db_session.execute(select(AtletaModel).filter_by(cpf=cpf_limpo))
    atleta = result.scalars().first()

    if not atleta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Atleta não encontrado com CPF: {cpf}",
        )

    return atleta


@router.patch(
    "/{id}",
    summary="Editar um Atleta pelo id",
    status_code=status.HTTP_200_OK,
    response_model=AtletaOut,
)
async def patch(
    id: UUID4, db_session: DatabaseDependency, atleta_up: AtletaUpdate = Body(...)
) -> AtletaOut:
    atleta: AtletaOut = (
        (await db_session.execute(select(AtletaModel).filter_by(id=id)))
        .scalars()
        .first()
    )

    if not atleta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Atleta não encontrado no id: {id}",
        )

    atleta_update = atleta_up.model_dump(exclude_unset=True)
    for key, value in atleta_update.items():
        setattr(atleta, key, value)

    await db_session.commit()
    await db_session.refresh(atleta)

    return atleta


@router.delete(
    "/{id}", summary="Deletar um Atleta pelo id", status_code=status.HTTP_204_NO_CONTENT
)
async def delete(id: UUID4, db_session: DatabaseDependency) -> None:
    atleta: AtletaOut = (
        (await db_session.execute(select(AtletaModel).filter_by(id=id)))
        .scalars()
        .first()
    )

    if not atleta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Atleta não encontrado no id: {id}",
        )

    await db_session.delete(atleta)
    await db_session.commit()


def limpar_cpf(cpf: str) -> str:
    """Remove formatação do CPF (pontos, traços, espaços)"""
    return re.sub(r"[^0-9]", "", cpf)


def validar_cpf(cpf: str) -> bool:
    """Valida CPF usando o algoritmo oficial"""
    cpf = limpar_cpf(cpf)

    # Verifica se tem 11 dígitos
    if len(cpf) != 11:
        return False

    # Verifica se não são todos números iguais
    if cpf == cpf[0] * 11:
        return False

    # Calcula o primeiro dígito verificador
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    resto = soma % 11
    digito1 = 0 if resto < 2 else 11 - resto

    # Calcula o segundo dígito verificador
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    resto = soma % 11
    digito2 = 0 if resto < 2 else 11 - resto

    # Verifica se os dígitos calculados conferem
    return cpf[-2:] == f"{digito1}{digito2}"
