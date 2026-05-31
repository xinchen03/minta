"""Seed experiment demo data for the Admin Experiment Dashboard.
Run: python seed_experiment.py

This creates fake data in context_retrieval_log, task_reward_log, and bandit_state
so the dashboard shows meaningful charts. Real data will come from actual user interactions
once logging is wired into the API endpoints.
"""
import os
import random
import mysql.connector
from datetime import datetime, timedelta

DATABASE_URL = os.environ.get("MINTA_DATABASE_URL", "sqlite:///./minta.db")
if DATABASE_URL.startswith("sqlite"):
    print("seed_experiment.py requires MySQL. Set MINTA_DATABASE_URL to a MySQL connection string.")
    exit(1)

# Parse MySQL DSN: mysql+mysqlconnector://user:pass@host:port/db
from urllib.parse import urlparse
parsed = urlparse(DATABASE_URL.replace("mysql+mysqlconnector://", "mysql://"))
conn = mysql.connector.connect(
    host=parsed.hostname or "localhost",
    port=parsed.port or 3306,
    user=parsed.username,
    password=parsed.password,
    database=parsed.path.lstrip("/").split("?")[0],
)
cursor = conn.cursor()

# Check existing users with experiment conditions
cursor.execute("SELECT id, username, experiment_condition FROM users WHERE experiment_condition IS NOT NULL")
users = cursor.fetchall()
if not users:
    print("No users with experiment_condition set. Creating demo users...")
    # Assign mixed conditions for A/B test
    cursor.execute("UPDATE users SET experiment_condition = 'control' WHERE id = 5")
    cursor.execute("UPDATE users SET experiment_condition = 'treatment' WHERE id = 8")
    cursor.execute("UPDATE users SET experiment_condition = 'control' WHERE id = 11")
    cursor.execute("UPDATE users SET experiment_condition = 'treatment' WHERE id = 12")
    cursor.execute("UPDATE users SET experiment_condition = 'control' WHERE id = 13")
    cursor.execute("UPDATE users SET experiment_condition = 'treatment' WHERE id = 14")
    conn.commit()
    cursor.execute("SELECT id, username, experiment_condition FROM users WHERE experiment_condition IS NOT NULL")
    users = cursor.fetchall()

print(f"Found {len(users)} experiment users:")
for u in users:
    print(f"  User {u[0]} ({u[1]}): {u[2]}")

# Clear existing seed data
cursor.execute("DELETE FROM context_retrieval_log")
cursor.execute("DELETE FROM task_reward_log")
cursor.execute("DELETE FROM bandit_state")
conn.commit()

# ── 1. Seed context_retrieval_log (30 days of data) ──
print("\nSeeding context_retrieval_log...")
policies = ['bm25', 'pcl_bandit']
count = 0
for day_offset in range(30):
    day = datetime.now() - timedelta(days=29 - day_offset)
    for user_id, username, condition in users:
        # 5-20 retrievals per user per day
        for _ in range(random.randint(5, 20)):
            policy = random.choice(policies)
            # As experiment progresses, pcl_bandit becomes more used than bm25
            if day_offset > 20 and random.random() < 0.4:
                policy = 'pcl_bandit'
            k_shown = random.randint(2, 6)
            # Generate 3-8 random context IDs
            n_ids = random.randint(3, 8)
            ctx_ids = ','.join([f'ctx-{random.randint(1,50)}' for _ in range(n_ids)])
            scores = ','.join([f'{random.random():.4f}' for _ in range(n_ids)])
            embedding = f'[{",".join(f"{random.random():.4f}" for _ in range(32))}]'
            sql = """INSERT INTO context_retrieval_log
                (user_id, session_id, task_embedding, ranked_context_ids, scores,
                 k_shown, exp_condition, context_count, policy, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            cursor.execute(sql, (
                user_id, f'session-{user_id}-{count}',
                embedding, ctx_ids, scores,
                k_shown, condition, n_ids, policy,
                day + timedelta(hours=random.randint(8, 22), minutes=random.randint(0, 59))
            ))
            count += 1
print(f"  Created {count} retrieval log entries")

# ── 2. Seed task_reward_log ──
print("Seeding task_reward_log...")
count = 0
for day_offset in range(30):
    day = datetime.now() - timedelta(days=29 - day_offset)
    for user_id, username, condition in users:
        # 2-8 tasks per user per day
        for _ in range(random.randint(2, 8)):
            iteration_count = random.randint(1, 5)
            direct_copy = 1 if random.random() < 0.4 else 0
            quality_rating = random.randint(1, 5) if random.random() < 0.6 else None
            context_count = random.randint(3, 12)

            # Treatment group should get slightly better rewards
            if condition == 'treatment':
                # Fewer iterations, more copies, higher quality
                iteration_count = max(1, iteration_count - random.randint(0, 1))
                direct_copy = 1 if random.random() < 0.55 else 0
                if quality_rating:
                    quality_rating = min(5, quality_rating + random.randint(0, 1))

            # Composite reward (lower iterations = higher reward, higher copy = higher reward)
            iter_score = max(0, 1 - (iteration_count - 1) * 0.2)
            copy_score = direct_copy * 0.4
            quality_score = (quality_rating or 3) * 0.08
            composite = round(iter_score + copy_score + quality_score, 4)

            sql = """INSERT INTO task_reward_log
                (user_id, session_id, exp_condition, context_count,
                 iteration_count, direct_copy, quality_rating, composite_reward, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            cursor.execute(sql, (
                user_id, f'session-{user_id}-{count}',
                condition, context_count,
                iteration_count, direct_copy, quality_rating, composite,
                day + timedelta(hours=random.randint(8, 22), minutes=random.randint(0, 59))
            ))
            count += 1
print(f"  Created {count} reward log entries")

# ── 3. Seed bandit_state ──
print("Seeding bandit_state...")
count = 0
for user_id, username, condition in users:
    # 8-20 unique arms per user
    used_ids = set()
    for _ in range(random.randint(8, 20)):
        while True:
            ctx_id = f'ctx-bandit-{user_id}-{random.randint(1,999)}'
            if ctx_id not in used_ids:
                used_ids.add(ctx_id)
                break
        # A matrix (identity + interactions)
        import json
        A = [[1.0 if i == j else 0.0 for i in range(5)] for j in range(5)]
        for i in range(5):
            A[i][i] += random.randint(1, 20) * 0.5
        b = [random.uniform(-0.5, 2.0) for _ in range(5)]
        pulled_count = random.randint(1, 50)
        # Treatment group has more pulls (algorithm is being used more)
        if condition == 'treatment':
            pulled_count = int(pulled_count * 1.3)

        sql = """INSERT INTO bandit_state
            (user_id, context_id, A_json, b_json, pulled_count, last_pulled_at, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        cursor.execute(sql, (
            user_id, ctx_id,
            json.dumps(A), json.dumps(b), pulled_count,
            datetime.now() - timedelta(hours=random.randint(0, 72)),
            datetime.now() - timedelta(days=random.randint(1, 30))
        ))
        count += 1
print(f"  Created {count} bandit arms")

conn.commit()
cursor.close()
conn.close()

print("\nDone! Demo data seeded. Refresh Admin > Experiment Dashboard.")
