from django.db import models
from django.contrib.auth.models import User

class JobDescription(models.Model):
       title = models.CharField(max_length=255)
       original_text = models.TextField()
       summary = models.TextField()
       required_skills = models.TextField()  # Comma-separated
       required_experience = models.FloatField()  # In years
       required_qualifications = models.TextField()

       def __str__(self):
           return self.title

class Candidate(models.Model):
       name = models.CharField(max_length=255)
       email = models.EmailField()
       cv_text = models.TextField()
       education = models.TextField()
       skills = models.TextField()  # Comma-separated
       experience = models.FloatField()  # In years
       certifications = models.TextField()

       def __str__(self):
           return self.name

class Match(models.Model):
       job_description = models.ForeignKey(JobDescription, on_delete=models.CASCADE)
       candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE)
       match_score = models.FloatField()

       def __str__(self):
           return f"{self.candidate.name} - {self.job_description.title} ({self.match_score})"

class UserProfile(models.Model):
       user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
       role = models.CharField(max_length=50, choices=[
           ('HR', 'Human Resources'),
           ('MANAGER', 'Recruitment Manager'),
           ('INTERVIEWER', 'Interviewer'),
       ], default='HR')
       department = models.CharField(max_length=100, blank=True, null=True)
       created_at = models.DateTimeField(auto_now_add=True)

       def __str__(self):
           return f"{self.user.username} ({self.role})"