import os
import uuid
import random
import sqlite3
import chess
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DB_PATH = "chess_puzzles.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS puzzles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fen TEXT NOT NULL,
        solution_moves TEXT NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS user_stats (
        user_id TEXT PRIMARY KEY,
        total_attempts INTEGER DEFAULT 0,
        correct_attempts INTEGER DEFAULT 0,
        current_streak INTEGER DEFAULT 0,
        max_streak INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')

    cur = conn.execute("SELECT COUNT(*) FROM puzzles")
    if cur.fetchone()[0] == 0:
        print("Generating 500 puzzles for the first start...")
        puzzles = generate_puzzles(500)
        conn.executemany("INSERT INTO puzzles (fen, solution_moves) VALUES (?, ?)", puzzles)
        print("Puzzles generated.")
    conn.commit()
    conn.close()

def generate_puzzles(num: int):
    puzzles = []
    seen_fens = set()
    while len(puzzles) < num:
        try:
            board = chess.Board(None)
            bk_sq = random.choice(chess.SQUARES)
            board.set_piece_at(bk_sq, chess.Piece(chess.KING, chess.BLACK))
            possible_wk = [sq for sq in chess.SQUARES if chess.square_distance(sq, bk_sq) > 1]
            if not possible_wk:
                continue
            wk_sq = random.choice(possible_wk)
            board.set_piece_at(wk_sq, chess.Piece(chess.KING, chess.WHITE))
            piece_type = random.choice([chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT])
            empty_squares = [sq for sq in chess.SQUARES if sq != bk_sq and sq != wk_sq]
            if not empty_squares:
                continue
            piece_sq = random.choice(empty_squares)
            board.set_piece_at(piece_sq, chess.Piece(piece_type, chess.WHITE))
            board.turn = chess.WHITE
            if not board.is_valid():
                continue
            mates = []
            for move in board.legal_moves:
                board.push(move)
                if board.is_checkmate():
                    mates.append(move)
                board.pop()
            if len(mates) == 1:
                fen = board.fen()
                if fen not in seen_fens:
                    puzzles.append((fen, mates[0].uci()))
                    seen_fens.add(fen)
        except Exception:
            continue
    return puzzles

@app.middleware("http")
async def user_middleware(request: Request, call_next):
    user_id = request.cookies.get("user_id")
    if not user_id:
        user_id = str(uuid.uuid4())
    request.state.user_id = user_id
    response = await call_next(request)
    if not request.cookies.get("user_id"):
        response.set_cookie(key="user_id", value=user_id, max_age=365*24*3600)
    return response

def get_or_create_user(user_id: str):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,))
    conn.execute("INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/puzzle/next")
async def next_puzzle(request: Request):
    get_or_create_user(request.state.user_id)
    conn = get_db()
    cur = conn.execute("SELECT id, fen FROM puzzles ORDER BY RANDOM() LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "No puzzles found")
    return {"id": row["id"], "fen": row["fen"]}

@app.post("/api/puzzle/check")
async def check_puzzle(request: Request):
    user_id = request.state.user_id
    data = await request.json()
    puzzle_id = data.get("puzzle_id")
    move = data.get("move")
    if not puzzle_id or not move:
        raise HTTPException(400, "puzzle_id and move are required")

    conn = get_db()
    cur = conn.execute("SELECT fen, solution_moves FROM puzzles WHERE id=?", (puzzle_id,))
    puzzle = cur.fetchone()
    if not puzzle:
        conn.close()
        raise HTTPException(404, "Puzzle not found")

    solution_moves = puzzle["solution_moves"].split()
    correct = move in solution_moves

    get_or_create_user(user_id)
    stats = conn.execute("SELECT total_attempts, correct_attempts, current_streak, max_streak FROM user_stats WHERE user_id=?", (user_id,)).fetchone()
    total = stats["total_attempts"] + 1
    correct_count = stats["correct_attempts"]
    streak = stats["current_streak"]
    max_streak = stats["max_streak"]

    if correct:
        correct_count += 1
        streak += 1
        if streak > max_streak:
            max_streak = streak
    else:
        streak = 0

    conn.execute("UPDATE user_stats SET total_attempts=?, correct_attempts=?, current_streak=?, max_streak=? WHERE user_id=?",
                 (total, correct_count, streak, max_streak, user_id))
    conn.commit()
    conn.close()

    return {
        "correct": correct,
        "solution": solution_moves,
        "message": "Correct!" if correct else f"Incorrect. The correct move is {', '.join(solution_moves)}"
    }

@app.get("/api/stats")
async def get_stats(request: Request):
    user_id = request.state.user_id
    get_or_create_user(user_id)
    conn = get_db()
    stats = conn.execute("SELECT total_attempts, correct_attempts, current_streak, max_streak FROM user_stats WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    total = stats["total_attempts"]
    correct = stats["correct_attempts"]
    accuracy = (correct / total * 100) if total > 0 else 0
    return {
        "total_attempts": total,
        "correct_attempts": correct,
        "current_streak": stats["current_streak"],
        "max_streak": stats["max_streak"],
        "accuracy": round(accuracy, 1)
    }

@app.post("/api/reset-stats")
async def reset_stats(request: Request):
    user_id = request.state.user_id
    conn = get_db()
    conn.execute("UPDATE user_stats SET total_attempts=0, correct_attempts=0, current_streak=0, max_streak=0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)