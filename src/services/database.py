import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


load_dotenv()

# Construimos la URL de conexión

DATABASE_URL = "mysql+pymysql://{user}:{password}@{host}:{port}/{db_name}".format(
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    db_name=os.getenv("DB_NAME")
)

# Generamos el motror de SQLAlchemy
engine = create_engine(DATABASE_URL, echo=False) # echo=True para debugging: Imprime las consultas SQL en consola

# Creamos la fábrica de sesiones
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)