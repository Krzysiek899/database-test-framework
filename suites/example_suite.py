import random
from typing import List
from datetime import datetime, timedelta
import os

from faker import Faker

from framework.core.decorators import Setup, Suite, Benchmark
from data.schema import (
    User, Course, Module, Lesson,
    Enrollment, Quiz, QuizQuestion, QuizAttempt, QuestionAnswer, Payment
)


# Map sizes to number of users (constant, doesn't change)
DATASET_SIZES = {
    "small": 1_000,
    "medium": 10_000,
    "large": 100_000,
}


@Setup
def global_setup(db) -> None:
    """Generate comprehensive dataset of users, courses, modules, lessons, quizzes, enrollments, and payments."""
    DATASET_SIZE = os.environ.get("DATASET_SIZE", "medium")
    INDEXED_MODE = os.environ.get("INDEXED_MODE", "false").lower() == "true"

    # Create indices if enabled
    if INDEXED_MODE:
        db.users.create_index("email", unique=True)
        db.courses.create_index("instructor_id")
        db.lessons.create_index("type")
        db.enrollments.create_index("user_id")
        db.enrollments.create_index("course_id")
        db.quiz_attempts.create_index("user_id")
        db.payments.create_index("status")
        print(f"✓ Created 7 indices")
    else:
        print(f"⊘ Skipped index creation (INDEXED_MODE={INDEXED_MODE})")

    fake = Faker()
    Faker.seed(42)
    random.seed(42)

    NUM_USERS = DATASET_SIZES.get(DATASET_SIZE, DATASET_SIZES["medium"])
    NUM_COURSES = max(5, NUM_USERS // 10)
    MODULES_PER_COURSE = 2
    LESSONS_PER_MODULE = 3
    QUIZZES_PER_COURSE = 1
    QUESTIONS_PER_QUIZ = 4
    ENROLLMENTS_PER_USER = 2
    ATTEMPTS_PER_QUIZ = 2
    PAYMENTS_PER_USER = 1

    # Generate users
    users: List[User] = []
    for user_id in range(1, NUM_USERS + 1):
        user = User(
            user_id=user_id,
            email=fake.unique.email(),
            password_hash=fake.sha256(),
            role=random.choice(["student", "instructor", "admin"]),
            created_at=fake.date_time_between(start_date="-2y", end_date="now")
        )
        users.append(user)

    # Generate courses with embedded modules/lessons
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

    # Generate quizzes with embedded questions
    quizzes: List[Quiz] = []
    question_id_counter = 1

    for course_id in range(1, NUM_COURSES + 1):
        for quiz_idx in range(1, QUIZZES_PER_COURSE + 1):
            quiz_id = (course_id - 1) * QUIZZES_PER_COURSE + quiz_idx
            questions = []

            for q_idx in range(1, QUESTIONS_PER_QUIZ + 1):
                question = QuizQuestion(
                    question_id=question_id_counter,
                    quiz_id=quiz_id,
                    question_text=fake.sentence(),
                    points=random.choice([1, 2, 5, 10])
                )
                questions.append(question)
                question_id_counter += 1

            quiz = Quiz(
                quiz_id=quiz_id,
                course_id=course_id,
                title=f"Quiz: {fake.sentence()}",
                questions=questions
            )
            quizzes.append(quiz)

    # Generate enrollments
    enrollments: List[Enrollment] = []
    enrollment_id_counter = 1

    for user_id in range(1, NUM_USERS + 1):
        num_enrollments = random.randint(1, ENROLLMENTS_PER_USER)
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

    # Generate quiz attempts with embedded answers
    quiz_attempts: List[QuizAttempt] = []
    attempt_id_counter = 1
    answer_id_counter = 1

    for quiz_id in range(1, len(quizzes) + 1):
        num_attempts = random.randint(1, ATTEMPTS_PER_QUIZ)
        attempting_users = random.sample(range(1, NUM_USERS + 1), min(num_attempts, NUM_USERS))

        for user_id in attempting_users:
            answers = []
            total_points = 0

            # Find questions for this quiz
            quiz_qs = [q for q in quizzes if q.quiz_id == quiz_id]
            if quiz_qs:
                for question in quiz_qs[0].questions:
                    points_awarded = random.choice([0, question.points])
                    total_points += points_awarded
                    answer = QuestionAnswer(
                        answer_id=answer_id_counter,
                        attempt_id=attempt_id_counter,
                        question_id=question.question_id,
                        answer_text=fake.sentence(),
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

    # Generate payments
    payments: List[Payment] = []
    payment_id_counter = 1

    for user_id in range(1, NUM_USERS + 1):
        num_payments = random.randint(0, PAYMENTS_PER_USER)
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

    # Insert all data
    db.users.insert_many(users)
    db.courses.insert_many(courses)
    db.lessons.insert_many(lesson_list_all)
    db.enrollments.insert_many(enrollments)
    db.quizzes.insert_many(quizzes)
    db.quiz_attempts.insert_many(quiz_attempts)
    db.payments.insert_many(payments)

    print(f"✓ Generated {len(users)} users, {len(courses)} courses, {len(enrollments)} enrollments, " +
          f"{len(quizzes)} quizzes, {len(quiz_attempts)} attempts, {len(payments)} payments")


@Suite("online_learning_platform_suite")
class OnlineLearningPlatformSuite:

    @Benchmark("count_all_users")
    def count_all_users(self, db):
        """Count total users in system."""
        return db.users.count()

    @Benchmark("count_all_courses")
    def count_all_courses(self, db):
        """Count total courses in system."""
        return db.courses.count()

    @Benchmark("find_courses_by_instructor")
    def find_courses_by_instructor(self, db):
        """Find courses by specific instructor."""
        return db.courses.count({"instructor_id": 1})

    @Benchmark("find_lessons_by_type")
    def find_lessons_by_type(self, db):
        """Find lessons of specific type (video, text, etc.)."""
        return db.lessons.count({"type": "video"})

    @Benchmark("find_enrollments_by_user")
    def find_enrollments_by_user(self, db):
        """Find all enrollments for a specific user."""
        return db.enrollments.count({"user_id": 1})

    @Benchmark("find_enrollments_by_course")
    def find_enrollments_by_course(self, db):
        """Find all users enrolled in a course."""
        return db.enrollments.count({"course_id": 1})

    @Benchmark("find_quiz_attempts_by_user")
    def find_quiz_attempts_by_user(self, db):
        """Find quiz attempts by specific user."""
        return db.quiz_attempts.count({"user_id": 1})

    @Benchmark("find_payments_by_status")
    def find_payments_by_status(self, db):
        """Find payments with specific status."""
        return db.payments.count({"status": "completed"})

    @Benchmark("scan_all_enrollments")
    def scan_all_enrollments(self, db):
        """Full table scan of enrollments."""
        return db.enrollments.count()

    @Benchmark("scan_all_quiz_attempts")
    def scan_all_quiz_attempts(self, db):
        """Full table scan of quiz attempts."""
        return db.quiz_attempts.count()

    @Benchmark("insert_single_course")
    def insert_single_course(self, db):
        """Insert and delete a single course."""
        course = Course(
            course_id=999999,
            title="Benchmark Test Course",
            instructor_id=1,
            created_at=datetime.now(),
            modules=[]
        )
        db.courses.insert(course)
        db.courses.delete({"course_id": 999999})

    @Benchmark("insert_single_enrollment")
    def insert_single_enrollment(self, db):
        """Insert and delete a single enrollment."""
        enrollment = Enrollment(
            enrollment_id=999999,
            user_id=1,
            course_id=1,
            progress=50.0
        )
        db.enrollments.insert(enrollment)
        db.enrollments.delete({"enrollment_id": 999999})

    @Benchmark("update_enrollment_progress")
    def update_enrollment_progress(self, db):
        """Update progress for an enrollment."""
        db.enrollments.update(
            {"enrollment_id": 1},
            {"progress": 75.5}
        )

    @Benchmark("update_lesson_order")
    def update_lesson_order(self, db):
        """Update order index for a lesson."""
        db.lessons.update(
            {"lesson_id": 1},
            {"order_index": 5}
        )

    @Benchmark("select_first_user")
    def select_first_user(self, db):
        """Select user with EXPLAIN."""
        result = db.users.select({"user_id": 1}, use_explain=True)
        return len(result) if result else 0

    @Benchmark("batch_insert_courses")
    def batch_insert_courses(self, db):
        """Insert multiple courses."""
        courses = []
        for i in range(10):
            course = Course(
                course_id=900000 + i,
                title=f"Batch Course {i}",
                instructor_id=random.randint(1, 50),
                created_at=datetime.now(),
                modules=[]
            )
            courses.append(course)
        db.courses.insert_many(courses)
        # Clean up
        for i in range(10):
            db.courses.delete({"course_id": 900000 + i})
