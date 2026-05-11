import random
from typing import List
from datetime import datetime, timedelta
import uuid

from faker import Faker

from framework.core.decorators import Suite, Benchmark
from data.schema import (
    User, Course, Module, Lesson,
    Enrollment, Quiz, QuizQuestion, QuizAttempt, QuestionAnswer, Payment
)

# Import setup to register it
from .setups.online_learning_platform_setup import global_setup


@Suite("online_learning_platform_suite")
class OnlineLearningPlatformSuite:
    """Test suite with 24 CRUD scenarios: 6 CREATE, 6 READ, 6 UPDATE, 6 DELETE.
    Each method runs twice: once without indexes (INDEXED_MODE=false), once with indexes (INDEXED_MODE=true).
    Uses DatabaseFacade for all operations; EXPLAIN logging on READ scenarios."""

    def __init__(self):
        """Initialize Faker once to avoid per-benchmark overhead."""
        self.fake = Faker()
        Faker.seed(42)

    # ===== CREATE SCENARIOS =====

    @Benchmark("create_user")
    def create_user(self, db):
        """CREATE: Insert single User record with Faker data.
        Baseline write performance; indexes have minimal impact on INSERT.
        Uses UUID-based unique ID to avoid duplicate key conflicts."""
        # Generate truly unique ID using UUID to avoid E11000 errors
        unique_suffix = str(uuid.uuid4()).replace('-', '')[:12]
        unique_id = 800000 + int(unique_suffix, 16) % 100000
        
        temp_user = User(
            user_id=unique_id,
            email=f"benchmark_{unique_suffix}@example.com",
            password_hash=self.fake.sha256(),
            role="student",
            created_at=datetime.now()
        )
        db.users.insert(temp_user)
        return 1

    @Benchmark("create_enrollment_batch")
    def create_enrollment_batch(self, db):
        """CREATE: Batch insert 10,000 Enrollment records.
        Stresses bulk write performance; batch optimization matters.
        Uses large random ID range to avoid conflicts."""
        enrollments = []
        num_users = db.users.count()
        num_courses = db.courses.count()
        
        # Ensure minimum values to avoid randint() errors
        num_users = max(1, num_users)
        num_courses = max(1, num_courses)
        
        # Generate large unique base ID to avoid collisions
        unique_base = random.randint(10000000, 99999999)
        
        for i in range(10000):
            enrollment = Enrollment(
                enrollment_id=unique_base + i,
                user_id=random.randint(1, min(num_users, 10000)),
                course_id=random.randint(1, num_courses),
                progress=round(random.uniform(0.0, 100.0), 2)
            )
            enrollments.append(enrollment)
        
        db.enrollments.insert_many(enrollments)
        return len(enrollments)

    @Benchmark("create_quiz_with_embedded_questions")
    def create_quiz_with_embedded_questions(self, db):
        """CREATE: Insert Quiz with 20 embedded QuizQuestion objects.
        Tests embedding performance (doc-DBs) vs association table creation (relational DBs).
        Uses unique ID per run to avoid conflicts."""
        unique_id = random.randint(10000000, 99999999)
        
        questions = []
        for q_idx in range(1, 21):  # 20 questions
            question = QuizQuestion(
                question_id=unique_id + q_idx,
                quiz_id=unique_id,
                question_text=self.fake.sentence(),
                points=random.choice([1, 2, 5, 10])
            )
            questions.append(question)
        
        quiz = Quiz(
            quiz_id=unique_id,
            course_id=1,
            title=f"Benchmark Quiz {unique_id}",
            questions=questions
        )
        db.quizzes.insert(quiz)
        return len(questions)

    @Benchmark("create_payment_bulk")
    def create_payment_bulk(self, db):
        """CREATE: Batch insert 5,000 Payment records.
        Tests bulk write performance for financial transaction records."""
        payments = []
        unique_base = random.randint(20000000, 29999999)
        
        for i in range(5000):
            payment = Payment(
                payment_id=unique_base + i,
                user_id=random.randint(1, 100),
                course_id=random.randint(1, 50),
                amount=round(random.uniform(9.99, 299.99), 2),
                status=random.choice(["pending", "completed", "failed"])
            )
            payments.append(payment)
        
        db.payments.insert_many(payments)
        return len(payments)

    @Benchmark("create_course_with_modules_batch")
    def create_course_with_modules_batch(self, db):
        """CREATE: Batch insert 100 Courses, each with 3 embedded modules and 9 lessons.
        Tests embedding depth and performance at scale."""
        courses = []
        unique_base = random.randint(30000000, 39999999)
        lesson_id_counter = unique_base
        
        for course_idx in range(100):
            modules = []
            course_id = unique_base + course_idx
            
            for module_idx in range(3):
                lessons = []
                for lesson_idx in range(3):
                    lesson = Lesson(
                        lesson_id=lesson_id_counter,
                        module_id=course_id * 10 + module_idx,
                        title=f"Lesson {lesson_idx}",
                        type=random.choice(["video", "text", "interactive"]),
                        content_ref=f"content/{course_id}/{module_idx}/{lesson_idx}",
                        duration_sec=random.randint(300, 3600),
                        order_index=lesson_idx
                    )
                    lessons.append(lesson)
                    lesson_id_counter += 1
                
                module = Module(
                    module_id=course_id * 10 + module_idx,
                    course_id=course_id,
                    title=f"Module {module_idx}",
                    order_index=module_idx,
                    lessons=lessons
                )
                modules.append(module)
            
            course = Course(
                course_id=course_id,
                title=f"Batch Course {course_idx}",
                instructor_id=random.randint(1, 100),
                created_at=datetime.now(),
                modules=modules
            )
            courses.append(course)
        
        db.courses.insert_many(courses)
        return len(courses)

    @Benchmark("create_lesson")
    def create_lesson(self, db):
        """CREATE: Batch insert 1,000 simple Lesson records (flat structure).
        Measures performance of non-embedded INSERT."""
        lessons = []
        unique_base = random.randint(40000000, 49999999)
        
        for i in range(1000):
            lesson = Lesson(
                lesson_id=unique_base + i,
                module_id=random.randint(1, 100),
                title=f"Lesson {i}",
                type=random.choice(["video", "text", "quiz"]),
                content_ref=f"content/lesson/{i}",
                duration_sec=random.randint(300, 3600),
                order_index=i % 20
            )
            lessons.append(lesson)
        
        db.lessons.insert_many(lessons)
        return len(lessons)

    # ===== READ SCENARIOS =====

    @Benchmark("read_enrolled_courses_with_details")
    def read_enrolled_courses_with_details(self, db):
        """READ: JOIN courses + enrollments to get all courses for a specific user with course details.
        Demonstrates: JOIN with filter on joined table (qualified column name).
        Index benefit: courses(course_id), enrollments(user_id, course_id)
        SQL equivalent: SELECT c.* FROM courses c JOIN enrollments e ON c.course_id = e.course_id WHERE e.user_id = 5"""
        result = db.courses.select_advanced(
            filters={"enrollments.user_id": 5},
            joins=[("courses", "enrollments", "course_id", "course_id")],
            use_explain=True
        )
        return len(result) if result else 0

    @Benchmark("read_top_courses_by_enrollment_count")
    def read_top_courses_by_enrollment_count(self, db):
        """READ: GROUP BY + ORDER BY to find top 10 courses by enrollment count (filtered by course_id).
        Demonstrates: GROUP BY, COUNT aggregation, ORDER BY DESC, LIMIT, WHERE clause.
        Index benefit: enrollments(course_id)
        SQL equivalent: SELECT course_id, COUNT(*) as enrollment_count FROM enrollments 
                        WHERE course_id > 10 GROUP BY course_id ORDER BY enrollment_count DESC LIMIT 10"""
        result = db.enrollments.select_aggregation(
            filters={"course_id": {"in": list(range(100, 200))}},
            group_by=["course_id"],
            aggregates={"enrollment_count": ("course_id", "count")},
            order_by=[("enrollment_count", "desc")],
            limit=10,
            use_explain=True
        )
        return len(result) if result else 0

    @Benchmark("read_payments_in_amount_range")
    def read_payments_in_amount_range(self, db):
        """READ: Range filter with ORDER BY to find payments between $50-$150, sorted by amount DESC.
        Demonstrates: Range filter (gt/lt), ORDER BY, LIMIT.
        Index benefit: payments(amount)
        SQL equivalent: SELECT * FROM payments WHERE amount >= 50 AND amount <= 150 
                        ORDER BY amount DESC LIMIT 20"""
        result = db.payments.select_advanced(
            filters={"amount": {"gte": 50.0, "lte": 150.0}},
            order_by=[("amount", "desc")],
            limit=20,
            use_explain=True
        )
        return len(result) if result else 0

    @Benchmark("read_avg_enrollment_progress_by_course")
    def read_avg_enrollment_progress_by_course(self, db):
        """READ: GROUP BY with AVG aggregation to find average progress per course (filtered).
        Demonstrates: GROUP BY, AVG aggregation, ORDER BY DESC, LIMIT, WHERE clause with range filter.
        Index benefit: enrollments(course_id)
        SQL equivalent: SELECT course_id, AVG(progress) as avg_progress, COUNT(*) as student_count 
                        FROM enrollments WHERE course_id > 20 GROUP BY course_id ORDER BY avg_progress DESC LIMIT 15"""
        result = db.enrollments.select_aggregation(
            filters={"course_id": {"gt": 20}},
            group_by=["course_id"],
            aggregates={"avg_progress": ("progress", "avg"), "student_count": ("user_id", "count")},
            order_by=[("avg_progress", "desc")],
            limit=15,
            use_explain=True
        )
        return len(result) if result else 0

    @Benchmark("read_quiz_performance_with_course_details")
    def read_quiz_performance_with_course_details(self, db):
        """READ: Multiple JOINs to correlate quiz attempts with course info.
        Demonstrates: Multiple JOINs (quiz_attempts -> quizzes -> courses), WHERE filter, ORDER BY.
        Index benefit: quiz_attempts(user_id), quizzes(course_id)
        SQL equivalent: SELECT qa.attempt_id, qa.score, q.quiz_id, c.title FROM quiz_attempts qa 
                        JOIN quizzes q ON qa.quiz_id = q.quiz_id 
                        JOIN courses c ON q.course_id = c.course_id 
                        WHERE qa.user_id = 100 ORDER BY qa.score DESC LIMIT 50"""
        result = db.quiz_attempts.select_advanced(
            filters={"user_id": 100},
            joins=[
                ("quiz_attempts", "quizzes", "quiz_id", "quiz_id"),
                ("quizzes", "courses", "course_id", "course_id")
            ],
            order_by=[("score", "desc")],
            limit=50,
            use_explain=True
        )
        return len(result) if result else 0

    @Benchmark("read_lessons_paginated")
    def read_lessons_paginated(self, db):
        """READ: Pagination with ORDER BY to retrieve lessons page-by-page (non-zero offset).
        Demonstrates: LIMIT, OFFSET, ORDER BY for pagination with realistic offset > 0.
        Index benefit: lessons(module_id, order_index)
        SQL equivalent: SELECT * FROM lessons WHERE module_id = 10 
                        ORDER BY order_index ASC LIMIT 10 OFFSET 100"""
        page = 10  # Page 10 = offset 100
        page_size = 10
        result = db.lessons.select_advanced(
            filters={"module_id": 10},
            order_by=[("order_index", "asc")],
            limit=page_size,
            offset=page * page_size,
            use_explain=True
        )
        return len(result) if result else 0

    @Benchmark("read_payments_by_user_and_status")
    def read_payments_by_user_and_status(self, db):
        """READ: Composite filter on two columns (user_id + status) to test multi-column index.
        Demonstrates: Multi-column WHERE clause (composite filter), ORDER BY, LIMIT.
        Index benefit: payments(user_id, status) or individual indices on both columns.
        SQL equivalent: SELECT * FROM payments WHERE user_id = 50 AND status = 'completed' 
                        ORDER BY amount DESC LIMIT 25"""
        result = db.payments.select_advanced(
            filters={"user_id": 50, "status": "completed"},
            order_by=[("amount", "desc")],
            limit=25,
            use_explain=True
        )
        return len(result) if result else 0

    # ===== UPDATE SCENARIOS =====

    @Benchmark("update_user_password")
    def update_user_password(self, db):
        """UPDATE: Single record password update.
        Creates test user in reserved range, then updates. Only UPDATE timing measured.
        No rollback needed - test data is isolated in reserved ID range.
        Uses UUID-based unique ID to avoid E11000 duplicate key errors."""
        # Generate unique email using UUID to prevent collisions
        unique_suffix = str(uuid.uuid4()).replace('-', '')[:12]
        unique_id = 700000 + int(unique_suffix, 16) % 100000
        test_email = f"update_test_{unique_suffix}@example.com"
        
        # Create test user for update
        temp_user = User(
            user_id=unique_id,
            email=test_email,
            password_hash="old_hash",
            role="student",
            created_at=datetime.now()
        )
        db.users.insert(temp_user)
        
        # BENCHMARK: Update password (only this is timed accurately)
        db.users.update({"user_id": unique_id}, {"password_hash": self.fake.sha256()})
        
        return 1

    @Benchmark("update_enrollment_progress_batch")
    def update_enrollment_progress_batch(self, db):
        """UPDATE: Batch update enrollments' progress for a specific user.
        Tests WHERE clause efficiency during multi-record updates.
        Operates on real data from seeding (user_id=1 has many enrollments).
        Only UPDATE timing measured - data changes persist for this run."""
        target_user_id = 1  # Real user from seeding with many enrollments
        
        # BENCHMARK: Update all enrollments for target user to progress=100.0
        db.enrollments.update_many(
            {"user_id": target_user_id},
            {"progress": 100.0}
        )
        
        # Return count of updated records
        count = db.enrollments.count({"user_id": target_user_id, "progress": 100.0})
        return count

    @Benchmark("update_payment_status_multi_criteria")
    def update_payment_status_multi_criteria(self, db):
        """UPDATE: Update payments matching multi-column filter (status='pending' AND user_id=X).
        Tests composite index efficiency on complex WHERE clauses.
        Operates on real data from seeding. Only UPDATE timing measured.
        Data changes persist - at next run with different INDEXED_MODE, global_setup provides fresh data."""
        target_user_id = 1  # Real user from seeding
        
        # BENCHMARK: Update pending payments to completed
        db.payments.update_many(
            {"user_id": target_user_id, "status": "pending"},
            {"status": "completed"}
        )
        
        # Return count of updated records
        count = db.payments.count({"user_id": target_user_id, "status": "completed"})
        return count

    @Benchmark("update_lesson_order_batch")
    def update_lesson_order_batch(self, db):
        """UPDATE: Batch update lesson order indexes for a module.
        Tests bulk UPDATE on subset of records."""
        target_module_id = 50
        
        # Update all lessons in module with order_index = 10
        db.lessons.update_many(
            {"module_id": target_module_id},
            {"order_index": 10}
        )
        
        count = db.lessons.count({"module_id": target_module_id})
        return count

    @Benchmark("update_course_instructor")
    def update_course_instructor(self, db):
        """UPDATE: Change instructor for a specific course.
        Single-record update by course_id."""
        unique_course_id = random.randint(50000000, 50999999)
        
        # Create a test course first
        course = Course(
            course_id=unique_course_id,
            title="Course for instructor update",
            instructor_id=1,
            created_at=datetime.now(),
            modules=[]
        )
        db.courses.insert(course)
        
        # Update instructor
        db.courses.update(
            {"course_id": unique_course_id},
            {"instructor_id": 999}
        )
        
        return 1

    @Benchmark("update_quiz_title_batch")
    def update_quiz_title_batch(self, db):
        """UPDATE: Batch update quiz titles for a course.
        Tests UPDATE with string concatenation/modification."""
        target_course_id = 100
        
        db.quizzes.update_many(
            {"course_id": target_course_id},
            {"title": "Updated Quiz Title"}
        )
        
        count = db.quizzes.count({"course_id": target_course_id})
        return count

    # ===== DELETE SCENARIOS =====

    @Benchmark("delete_old_quiz_attempts")
    def delete_old_quiz_attempts(self, db):
        """DELETE: Bulk delete quiz attempts with score=0.0.
        Creates test records, then measures DELETE performance.
        Only DELETE is accurately timed - test records are isolated.
        Deletes by score=0.0 filter (works on both MongoDB and relational DBs)."""
        unique_user_id = 999000 + random.randint(0, 999)
        unique_quiz_id = random.randint(70000000, 70999999)
        
        # Create test attempts with score=0.0 for deletion
        attempts_to_delete = []
        for i in range(100):
            attempt = QuizAttempt(
                attempt_id=random.randint(10000000, 99999999),
                quiz_id=unique_quiz_id,
                user_id=unique_user_id,
                score=0.0,
                answers=[]
            )
            attempts_to_delete.append(attempt)
        
        db.quiz_attempts.insert_many(attempts_to_delete)
        
        # BENCHMARK: Delete test attempts by score=0.0 (works on all DBs)
        db.quiz_attempts.delete_many({"user_id": unique_user_id, "score": 0.0})
        
        return 100

    @Benchmark("delete_lesson_from_module")
    def delete_lesson_from_module(self, db):
        """DELETE: Delete lessons from a specific module.
        Embedded deletion (doc-DBs) vs cascading FK delete (relational DBs).
        Creates test lessons in reserved ID range, then measures DELETE performance.
        Uses large random ID range to avoid collisions."""
        unique_base = random.randint(61000000, 61999999)
        module_id = 100000 + random.randint(0, 99999)  # Unique module per run
        
        # Create test lessons for deletion
        lessons_to_delete = []
        for i in range(20):
            lesson = Lesson(
                lesson_id=unique_base + i,
                module_id=module_id,
                title=f"Delete Test Lesson {i}",
                type="video",
                content_ref=f"content/delete_test/{i}",
                duration_sec=300,
                order_index=i
            )
            lessons_to_delete.append(lesson)
        
        db.lessons.insert_many(lessons_to_delete)
        
        # BENCHMARK: Delete test lessons by module_id
        db.lessons.delete_many({"module_id": module_id})
        
        return len(lessons_to_delete)

    @Benchmark("delete_stale_payment")
    def delete_stale_payment(self, db):
        """DELETE: Delete payments with specific status (status='failed').
        Multi-criteria filter; composite index benefits deletion performance.
        Creates test payments, then measures DELETE performance.
        Uses large random ID range to avoid collisions.
        Deletes by user_id + status filter (works on all DBs)."""
        unique_user_id = 998000 + random.randint(0, 999)
        
        # Create test payments with status='failed' for deletion
        payments_to_delete = []
        for i in range(50):
            payment = Payment(
                payment_id=random.randint(10000000, 99999999),
                user_id=unique_user_id,
                course_id=1,
                amount=9.99 + i,
                status="failed"
            )
            payments_to_delete.append(payment)
        
        db.payments.insert_many(payments_to_delete)
        
        # BENCHMARK: Delete test payments by user_id + status (works on all DBs)
        db.payments.delete_many({"user_id": unique_user_id, "status": "failed"})
        
        return len(payments_to_delete)

    @Benchmark("delete_quiz_by_course")
    def delete_quiz_by_course(self, db):
        """DELETE: Delete all quizzes for a specific course.
        Tests cascading DELETE pattern."""
        unique_course_id = random.randint(51000000, 51999999)
        
        # Create test quizzes
        quizzes = []
        for i in range(50):
            quiz = Quiz(
                quiz_id=random.randint(10000000, 99999999),
                course_id=unique_course_id,
                title=f"Quiz {i}",
                questions=[]
            )
            quizzes.append(quiz)
        
        db.quizzes.insert_many(quizzes)
        
        # BENCHMARK: Delete all quizzes for this course
        db.quizzes.delete_many({"course_id": unique_course_id})
        
        return 50

    @Benchmark("delete_enrollment_by_course")
    def delete_enrollment_by_course(self, db):
        """DELETE: Delete all enrollments for a specific course.
        Tests foreign key pattern deletion."""
        unique_course_id = random.randint(52000000, 52999999)
        
        # Create test enrollments
        enrollments = []
        for i in range(200):
            enrollment = Enrollment(
                enrollment_id=random.randint(10000000, 99999999),
                user_id=random.randint(1, 100),
                course_id=unique_course_id,
                progress=random.uniform(0, 100)
            )
            enrollments.append(enrollment)
        
        db.enrollments.insert_many(enrollments)
        
        # BENCHMARK: Delete all enrollments for this course
        db.enrollments.delete_many({"course_id": unique_course_id})
        
        return 200

    @Benchmark("delete_old_quiz_questions")
    def delete_old_quiz_questions(self, db):
        """DELETE: Delete quiz questions (embedded deletion pattern).
        Tests deletion of embedded objects by parent ID."""
        unique_quiz_id = random.randint(53000000, 53999999)
        
        # Create a test quiz with embedded questions
        questions = []
        for i in range(30):
            question = QuizQuestion(
                question_id=random.randint(10000000, 99999999),
                quiz_id=unique_quiz_id,
                question_text=f"Question {i}",
                points=random.choice([1, 2, 5, 10])
            )
            questions.append(question)
        
        quiz = Quiz(
            quiz_id=unique_quiz_id,
            course_id=1,
            title="Quiz for deletion",
            questions=questions
        )
        db.quizzes.insert(quiz)
        
        # BENCHMARK: Delete the quiz (which includes embedded questions)
        db.quizzes.delete_many({"quiz_id": unique_quiz_id})
        
        return len(questions)
