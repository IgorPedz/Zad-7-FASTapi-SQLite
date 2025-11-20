from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from datetime import datetime
from typing import Optional, List
import re
from difflib import SequenceMatcher

DATABASE_URL = "sqlite:///./animals.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Animal(Base):
    __tablename__ = "animals"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(30), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)

app = FastAPI(title="FASTapi - zarządanie zwierzętami")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class AnimalNotFound(Exception):
    pass


class InvalidNameFormat(Exception):
    pass


class DuplicateName(Exception):
    pass


class InvalidSortParameter(Exception):
    pass


class SearchNotFound(Exception):
    pass


@app.exception_handler(AnimalNotFound)
async def not_found_handler(_, exc: AnimalNotFound):
    return JSONResponse(status_code=404, content={"error": "Nie znalezione zwierze!", "message": str(exc)})


@app.exception_handler(InvalidNameFormat)
async def invalid_name(_, exc: InvalidNameFormat):
    return JSONResponse(status_code=400, content={"error": "Niepoprawny format nazwy!", "message": str(exc)})


@app.exception_handler(DuplicateName)
async def duplicate_name(_, exc: DuplicateName):
    return JSONResponse(status_code=400, content={"error": "Powtórka imienia!", "message": str(exc)})


@app.exception_handler(InvalidSortParameter)
async def invalid_sort(_, exc: InvalidSortParameter):
    return JSONResponse(status_code=400, content={"error": "Niepoprawny parametr sortowania", "message": str(exc)})


@app.exception_handler(SearchNotFound)
async def search_not_found(_, exc: SearchNotFound):
    return JSONResponse(status_code=404, content={"error": "Nie znaleziono takiego wyszukiwania", "message": str(exc)})


def validate_name(name: str):
    if len(name) < 2:
        raise InvalidNameFormat("Nazwa musi mieć co najmniej 2 znaki.")

    if len(name) > 30:
        raise InvalidNameFormat("Nazwa może mieć maksymalnie 30 znaków.")

    if name[-1] == " ":
        raise InvalidNameFormat("Nazwa nie może kończyć się spacją.")

    if not re.match(r"^[A-Za-z\-]+$", name):
        raise InvalidNameFormat("Nazwa może zawierać tylko litery i myślniki.")

    return name

@app.get("/animals/search")
def search_animals(name: str, db: Session = Depends(get_db)):
    name_lower = name.lower()

    filtered = db.query(Animal).filter(
        func.lower(Animal.name).like(f"%{name_lower}%")
    ).all()

    if not filtered:
        all_animals = db.query(Animal).all()
        filtered = [
            a for a in all_animals
            if SequenceMatcher(None, name_lower, a.name.lower()).ratio() >= 0.6
        ]

    if not filtered:
        raise SearchNotFound("Nie znaleziono wyników.")

    return filtered


@app.get("/animals")
def list_animals(
    sort: Optional[str] = Query(None, alias="Parametr sortowania"),
    from_date: Optional[str] = Query(None, alias="Od"),
    to_date: Optional[str] = Query(None, alias="Do"),
    db: Session = Depends(get_db)
):
    query = db.query(Animal)

    if from_date:
        query = query.filter(Animal.created_at >= datetime.fromisoformat(from_date))

    if to_date:
        query = query.filter(Animal.created_at <= datetime.fromisoformat(to_date))

    if sort:
        if sort == "name":
            query = query.order_by(Animal.name.asc())
        elif sort == "-name":
            query = query.order_by(Animal.name.desc())
        else:
            raise InvalidSortParameter("Dozwolone wartości to: name, -name")

    return query.all()


@app.get("/animals/{id}")
def get_animal(id: int, db: Session = Depends(get_db)):
    animal = db.query(Animal).filter(Animal.id == id).first()
    if not animal:
        raise AnimalNotFound(f"Zwierzę o id {id} nie istnieje.")
    return animal


@app.post("/animals")
def add_animal(name: str, db: Session = Depends(get_db)):
    name = validate_name(name)

    if db.query(Animal).filter(func.lower(Animal.name) == name.lower()).first():
        raise DuplicateName("Zwierzę o podanej nazwie już istnieje.")

    animal = Animal(name=name)
    db.add(animal)
    db.commit()
    db.refresh(animal)
    return animal


@app.put("/animals/{id}")
def update_animal(id: int, name: str, db: Session = Depends(get_db)):
    validate_name(name)

    animal = db.query(Animal).filter(Animal.id == id).first()
    if not animal:
        raise AnimalNotFound(f"Zwierzę o id {id} nie istnieje.")

    if db.query(Animal).filter(func.lower(Animal.name) == name.lower(), Animal.id != id).first():
        raise DuplicateName("Zwierzę o podanej nazwie już istnieje.")

    animal.name = name
    db.commit()
    db.refresh(animal)
    return animal

@app.delete("/animals/{id}")
def delete_animal(id: int, db: Session = Depends(get_db)):
    animal = db.query(Animal).filter(Animal.id == id).first()
    if not animal:
        raise AnimalNotFound(f"Zwierzę o id {id} nie istnieje.")

    db.delete(animal)
    db.commit()
    return {"message": "Usunięto"}


