import random
from typing import List
from datetime import datetime
import os
import sys

from faker import Faker

from framework.core.decorators import Setup
from data.schema import (
    User, Course, Module, Lesson,
    Enrollment, Quiz, QuizQuestion, QuizAttempt, QuestionAnswer, Payment
)


# Map sizes to number of users (constant, doesn't change)
DATASET_SIZES = {
    "small": 10_000,
    "medium": 100_000,
    "large": 1_000_000,
}

BATCH_SIZE = 100_000  # Records per insert_many() call - increased for faster inserts


# Pre-generate fake data to avoid expensive operations in loops
def _generate_email(user_id: int) -> str:
    """Generate simple but unique email addresses."""
    return f"user{user_id}@example.com"


def _generate_password_hash() -> str:
    """Generate simple password hashes."""
    return "sha256_" + os.urandom(16).hex()[:40]


def _batch_insert(db, table_name, items: List, batch_size: int = BATCH_SIZE) -> int:
    """Helper: Insert items in batches to avoid memory overflow."""
    total_inserted = 0
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        db.__getattr__(table_name).insert_many(batch)
        total_inserted += len(batch)
    return total_inserted


@Setup
def global_setup(db) -> None:
    """Generate comprehensive dataset of users, courses, modules, lessons, quizzes, enrollments, and payments.
    Uses optimized batch insertion to handle large datasets efficiently."""
    DATASET_SIZE = os.environ.get("DATASET_SIZE", "medium")
    INDEXED_MODE = os.environ.get("INDEXED_MODE", "false").lower() == "true"

    # Create indices if enabled
    if INDEXED_MODE:
        db.users.create_index("email", unique=True)
        db.courses.create_index("instructor_id")
        db.courses.create_index("title")
        db.lessons.create_index("module_id")
        db.lessons.create_index("order_index")
        db.enrollments.create_index("user_id")
        db.enrollments.create_index("course_id")
        db.quiz_attempts.create_index("user_id")
        db.quiz_attempts.create_index("score")
        db.payments.create_index("status")
        db.payments.create_index("user_id")
        db.payments.create_index("amount")
        print(f"Created 13 indices (INDEXED_MODE=true)", flush=True)
    else:
        print(f"Skipped index creation (INDEXED_MODE=false)", flush=True)

    fake = Faker()
    Faker.seed(42)
    random.seed(42)

    NUM_USERS = DATASET_SIZES.get(DATASET_SIZE, DATASET_SIZES["medium"])
    
    NUM_COURSES = max(20, int(NUM_USERS * 0.08))    
    MODULES_PER_COURSE = random.randint(2, 5)    
    LESSONS_PER_MODULE = random.randint(3, 8)    
    QUIZZES_PER_COURSE = random.choice([0, 1, 2, 3])    
    QUESTIONS_PER_QUIZ = random.randint(3, 15)
    
    def get_enrollments_per_user():
        return random.choices(
            [1, 3, 5, 10],
            weights=[40, 25, 10, 3]
        )[0]
    
    ENROLLMENTS_PER_USER = None  # dynamic per user
    
    def get_attempts_per_quiz():
        return random.choices(
            [1, 3, 5],
            weights=[30, 50, 5]
        )[0]
    
    ATTEMPTS_PER_QUIZ = None  # dynamic per quiz
    
    PAYING_USERS_RATIO = 0.2  # 20% users pay
    
    def get_payments_per_user():
        return random.choices(
            [0, 1, 2, 3],
            weights=[50, 30, 15, 5]
        )[0]

    # ===== USERS =====
    print(f"Generating {NUM_USERS} users...", flush=True)
    users: List[User] = []
    for user_id in range(1, NUM_USERS + 1):
        user = User(
            user_id=user_id,
            email=_generate_email(user_id),
            password_hash=_generate_password_hash(),
            role=random.choice(["student", "instructor", "admin"]),
            created_at=fake.date_time_between(start_date="-2y", end_date="now")
        )
        users.append(user)
    _batch_insert(db, "users", users)
    print(f"Inserted {len(users)} users", flush=True)

    # ===== COURSES WITH EMBEDDED MODULES/LESSONS =====
    print(f"Generating {NUM_COURSES} courses with modules and lessons...", flush=True)
    courses: List[Course] = []
    lesson_id_counter = 1
    lesson_list_all: List[Lesson] = []

    for course_id in range(1, NUM_COURSES + 1):
        instructor_id = random.randint(1, NUM_USERS)
        modules = []

        for module_idx in range(1, MODULES_PER_COURSE + 1):
            module_id = (course_id - 1) * MODULES_PER_COURSE + module_idx
            lessons = []

            for lesson_idx in range(1, LESSONS_PER_MODULE + 1):
                lesson = Lesson(
                    lesson_id=lesson_id_counter,
                    module_id=module_id,
                    title=f"Lesson {lesson_idx}: {fake.sentence()}",
                    type=random.choice(["video", "text", "interactive", "quiz"]),
                    content_ref=f"content/{course_id}/{module_id}/{lesson_id_counter}",
                    duration_sec=random.randint(300, 3600),
                    order_index=lesson_idx
                )
                lessons.append(lesson)
                lesson_list_all.append(lesson)
                lesson_id_counter += 1

            module = Module(
                module_id=module_id,
                course_id=course_id,
                title=f"Module {module_idx}: {fake.sentence()}",
                order_index=module_idx,
                lessons=lessons
            )
            modules.append(module)

        course = Course(
            course_id=course_id,
            title=fake.sentence(),
            instructor_id=instructor_id,
            created_at=fake.date_time_between(start_date="-2y", end_date="now"),
            modules=modules
        )
        courses.append(course)
    
    _batch_insert(db, "courses", courses)
    _batch_insert(db, "lessons", lesson_list_all)
    print(f"Inserted {len(courses)} courses and {len(lesson_list_all)} lessons", flush=True)

    # ===== QUIZZES WITH EMBEDDED QUESTIONS =====
    print(f"Generating quizzes with embedded questions...", flush=True)
    quizzes: List[Quiz] = []
    question_id_counter = 1
    quiz_id_counter = 1

    for course_id in range(1, NUM_COURSES + 1):
        num_quizzes_for_course = QUIZZES_PER_COURSE
        for quiz_idx in range(1, num_quizzes_for_course + 1):
            questions = []

            for q_idx in range(1, QUESTIONS_PER_QUIZ + 1):
                question = QuizQuestion(
                    question_id=question_id_counter,
                    quiz_id=quiz_id_counter,
                    question_text=fake.sentence(),
                    points=random.choice([1, 2, 5, 10])
                )
                questions.append(question)
                question_id_counter += 1

            quiz = Quiz(
                quiz_id=quiz_id_counter,
                course_id=course_id,
                title=f"Quiz: {fake.sentence()}",
                questions=questions
            )
            quizzes.append(quiz)
            quiz_id_counter += 1
    
    _batch_insert(db, "quizzes", quizzes)
    print(f"Inserted {len(quizzes)} quizzes", flush=True)

    # ===== ENROLLMENTS =====
    print(f"Generating enrollments...", flush=True)
    enrollments: List[Enrollment] = []
    enrollment_id_counter = 1

    for user_id in range(1, NUM_USERS + 1):
        num_enrollments = get_enrollments_per_user()
        enrolled_courses = random.sample(range(1, NUM_COURSES + 1), min(num_enrollments, NUM_COURSES))

        for course_id in enrolled_courses:
            enrollment = Enrollment(
                enrollment_id=enrollment_id_counter,
                user_id=user_id,
                course_id=course_id,
                progress=round(random.uniform(0.0, 100.0), 2)
            )
            enrollments.append(enrollment)
            enrollment_id_counter += 1
    
    _batch_insert(db, "enrollments", enrollments)
    print(f"Inserted {len(enrollments)} enrollments", flush=True)

    # ===== QUIZ ATTEMPTS WITH EMBEDDED ANSWERS =====
    print(f"Generating quiz attempts with embedded answers...", flush=True)
    quiz_attempts: List[QuizAttempt] = []
    attempt_id_counter = 1
    answer_id_counter = 1

    # Map quizzes by ID for O(1) lookup instead of O(n) search
    quiz_map = {q.quiz_id: q for q in quizzes}

    for quiz_id, quiz in quiz_map.items():
        num_attempts = get_attempts_per_quiz()
        # For large datasets, sample fewer users
        max_users_to_sample = min(num_attempts, 100 if DATASET_SIZE == "large" else NUM_USERS)
        attempting_users = random.sample(range(1, NUM_USERS + 1), min(max_users_to_sample, NUM_USERS))

        for user_id in attempting_users:
            answers = []
            total_points = 0

            for question in quiz.questions:
                points_awarded = random.choice([0, question.points])
                total_points += points_awarded
                answer = QuestionAnswer(
                    answer_id=answer_id_counter,
                    attempt_id=attempt_id_counter,
                    question_id=question.question_id,
                    answer_text=f"answer_{answer_id_counter}",
                    points_awarded=float(points_awarded)
                )
                answers.append(answer)
                answer_id_counter += 1

            attempt = QuizAttempt(
                attempt_id=attempt_id_counter,
                quiz_id=quiz_id,
                user_id=user_id,
                score=float(total_points),
                answers=answers
            )
            quiz_attempts.append(attempt)
            attempt_id_counter += 1
    
    _batch_insert(db, "quiz_attempts", quiz_attempts)
    print(f"Inserted {len(quiz_attempts)} quiz attempts", flush=True)

    # ===== PAYMENTS =====
    print(f"Generating payments...", flush=True)
    payments: List[Payment] = []
    payment_id_counter = 1

    for user_id in range(1, NUM_USERS + 1):
        # Only 20% of users pay
        if random.random() < PAYING_USERS_RATIO:
            num_payments = get_payments_per_user()
            for _ in range(num_payments):
                course_id = random.randint(1, NUM_COURSES)
                payment = Payment(
                    payment_id=payment_id_counter,
                    user_id=user_id,
                    course_id=course_id,
                    amount=round(random.uniform(9.99, 199.99), 2),
                    status=random.choice(["pending", "completed", "failed", "refunded"])
                )
                payments.append(payment)
                payment_id_counter += 1
    
    _batch_insert(db, "payments", payments)
    print(f"Inserted {len(payments)} payments", flush=True)

    print(f"\nSetup complete: {len(users)} users, {len(courses)} courses, {len(enrollments)} enrollments, " +
          f"{len(quizzes)} quizzes, {len(quiz_attempts)} attempts, {len(payments)} payments", flush=True)
