from pydantic import BaseModel, Field


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(alias="newPassword")

    class Config:
        populate_by_name = True


class DeleteAccountRequest(BaseModel):
    password: str


class UserResponse(BaseModel):
    id: int
    name: str
    email: str


class MessageResponse(BaseModel):
    message: str
