from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from framework.core.decorators import Table


# ============================================================================
# 1. USERS
# ============================================================================

@Table("users")
class User(BaseModel):
    user_id: int
    email: str
    password_hash: str
    role: str
    created_at: datetime


# ============================================================================
# 4. LESSONS (leaf node - defined first for forward reference)
# ============================================================================

@Table("lessons")
class Lesson(BaseModel):
    lesson_id: int
    module_id: int
    title: str
    type: str
    content_ref: str
    duration_sec: int
    order_index: int


# ============================================================================
# 3. MODULES
# ============================================================================

@Table("modules")
class Module(BaseModel):
    module_id: int
    course_id: int
    title: str
    order_index: int
    lessons: List[Lesson] = Field(default_factory=list)  # For MongoDB embedding


# ============================================================================
# 2. COURSES
# ============================================================================

@Table("courses")
class Course(BaseModel):
    course_id: int
    title: str
    instructor_id: int
    created_at: datetime
    modules: List[Module] = Field(default_factory=list)  # For MongoDB embedding


# ============================================================================
# 5. ENROLLMENTS
# ============================================================================

@Table("enrollments")
class Enrollment(BaseModel):
    enrollment_id: int
    user_id: int
    course_id: int
    progress: float


# ============================================================================
# 7. QUIZ QUESTIONS (leaf node - defined first for forward reference)
# ============================================================================

@Table("quiz_questions")
class QuizQuestion(BaseModel):
    question_id: int
    quiz_id: int
    question_text: str
    points: int


# ============================================================================
# 6. QUIZZES
# ============================================================================

@Table("quizzes")
class Quiz(BaseModel):
    quiz_id: int
    course_id: int
    title: str
    questions: List[QuizQuestion] = Field(default_factory=list)  # For MongoDB embedding


# ============================================================================
# 9. QUESTION ANSWERS (leaf node - defined first for forward reference)
# ============================================================================

@Table("question_answers")
class QuestionAnswer(BaseModel):
    answer_id: int
    attempt_id: int
    question_id: int
    answer_text: str
    points_awarded: float


# ============================================================================
# 8. QUIZ ATTEMPTS
# ============================================================================

@Table("quiz_attempts")
class QuizAttempt(BaseModel):
    attempt_id: int
    quiz_id: int
    user_id: int
    score: float
    answers: List[QuestionAnswer] = Field(default_factory=list)  # For MongoDB embedding


# ============================================================================
# 10. PAYMENTS
# ============================================================================

@Table("payments")
class Payment(BaseModel):
    payment_id: int
    user_id: int
    course_id: int
    amount: float
    status: str
