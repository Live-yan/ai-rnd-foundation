from diagrams import Diagram
from diagrams.onprem.client import Users
from diagrams.onprem.compute import Server
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.inmemory import Redis

def render(filename):
    with Diagram("Generated product deployment", filename=str(filename), outformat="svg", show=False):
        user = Users("User")
        web = Server("Vue / FastAPI")
        user >> web
        web >> PostgreSQL("PostgreSQL")
        web >> Redis("Sessions")

if __name__ == "__main__":
    from pathlib import Path
    render(Path(__file__).with_name("deployment"))
