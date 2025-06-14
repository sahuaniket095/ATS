from django.shortcuts import render, redirect

from django.contrib.auth import authenticate, login, logout

from django.contrib.auth.forms import UserCreationForm

from django.core.files.storage import FileSystemStorage

from django.contrib import messages

from django.contrib.auth.decorators import login_required

import os


from .models import Candidate

from .utils import summarize_jd, extract_cv_data, calculate_match_score, send_interview_email, send_custom_email


from django.conf import settings

from .models import UserProfile

from django.contrib.auth.views import LoginView

import logging



logger = logging.getLogger(__name__)



class CustomLoginView(LoginView):

    def form_invalid(self, form):

        logger.error(f"Login failed: {form.errors}")

        return super().form_invalid(form)



def register(request):

    if request.method == 'POST':

        form = UserCreationForm(request.POST)

        if form.is_valid():

            user = form.save()

            UserProfile.objects.create(user=user, role='HR')

            username = form.cleaned_data.get('username')

            messages.success(request, f'Account created for {username}! Please log in.')

            return redirect('login')

        else:

            for field, errors in form.errors.items():

                for error in errors:

                    messages.error(request, f"{field}: {error}")

    else:

        form = UserCreationForm()

    return render(request, 'recruitment/register.html', {'form': form})





def user_login(request):

    if request.method == 'POST':

        username = request.POST['username']

        password = request.POST['password']

        user = authenticate(request, username=username, password=password)

        if user is not None:

            login(request, user)

            return redirect('upload')  # Redirect to upload page after login

        else:

            messages.error(request, 'Invalid username or password.')

    return render(request, 'recruitment/login.html', {})



def user_logout(request):

    logout(request)

    messages.success(request, 'You have been logged out.')

    return redirect('login')



@login_required

def upload(request):
    """Handle JD and CV uploads, process files, and shortlist candidates."""
    if request.method == 'POST':
        try:
            jd_file = request.FILES.get('jd_file')
            cv_files = request.FILES.getlist('cv_files')
            
            if not jd_file:
                logger.error("No JD file uploaded")
                return render(request, 'recruitment/upload.html', {'error': 'Please upload a job description file'})
            
            if not cv_files:
                logger.error("No CV files uploaded")
                return render(request, 'recruitment/upload.html', {'error': 'Please upload at least one CV file'})
            
            # Process JD
            jd_result = summarize_jd(jd_file)
            logger.debug(f"JD result: {jd_result}")
            
            if not jd_result or 'summary' not in jd_result or not jd_result.get('summary'):
                logger.warning("Empty JD summary")
                return render(request, 'recruitment/upload.html', {'error': 'Failed to process job description'})
            
            job_title = jd_result.get('job_title', 'Unknown Job Title')
            jd_summary = jd_result.get('summary', '')
            
            # Process CVs
            candidates = []
            for cv_file in cv_files:
                try:
                    cv_data = extract_cv_data(cv_file)
                    logger.debug(f"CV data for {cv_file.name}: {cv_data}")
                    
                    if not cv_data or not cv_data.get('name') or not cv_data.get('email'):
                        logger.warning(f"Invalid CV data for {cv_file.name}")
                        continue
                    
                    # Calculate match score
                    match_score = calculate_match_score(cv_data, jd_summary)
                    logger.debug(f"Match score for {cv_data['name']}: {match_score}")
                    
                    # Save CV file
                    fs = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'cvs'))
                    cv_filename = fs.save(cv_file.name, cv_file)
                    
                    # Save candidate to database
                    candidate = Candidate(
                        name=cv_data['name'],
                        email=cv_data['email'],
                        cv_file=os.path.join('cvs', cv_filename),
                        job_title=job_title,
                        match_score=match_score,
                        is_shortlisted=match_score >= 70  # Threshold for shortlisting
                    )
                    candidate.save()
                    
                    # Send interview email if shortlisted
                    if candidate.is_shortlisted:
                        try:
                            send_interview_email(candidate.email, candidate.name, job_title)
                            logger.info(f"Interview email sent to {candidate.email}")
                        except Exception as e:
                            logger.error(f"Failed to send interview email to {candidate.email}: {str(e)}")
                    
                    candidates.append({
                        'name': candidate.name,
                        'email': candidate.email,
                        'match_score': match_score,
                        'is_shortlisted': candidate.is_shortlisted
                    })
                
                except Exception as e:
                    logger.error(f"Error processing CV {cv_file.name}: {str(e)}")
                    continue
            
            if not candidates:
                logger.warning("No valid candidates processed")
                return render(request, 'recruitment/upload.html', {'error': 'No valid CVs processed'})
            
            context = {
                'job_title': job_title,
                'candidates': candidates,
                'success': 'Files processed successfully',
            }
            return render(request, 'recruitment/upload.html', context)
        
        except Exception as e:
            logger.error(f"Error in upload view: {str(e)}")
            return render(request, 'recruitment/upload.html', {'error': 'An unexpected error occurred'})
    
    return render(request, 'recruitment/upload.html')

def shortlisted_candidates(request):
    """Display shortlisted candidates."""
    try:
        candidates = Candidate.objects.filter(is_shortlisted=True).order_by('-match_score')
        context = {
            'candidates': candidates,
        }
        return render(request, 'recruitment/shortlisted.html', context)
    except Exception as e:
        logger.error(f"Error in shortlisted_candidates view: {str(e)}")
        return render(request, 'recruitment/shortlisted.html', {'error': 'Failed to load shortlisted candidates'})

def send_custom_email(request):
    """Handle sending custom emails to candidates."""
    if request.method == 'POST':
        try:
            candidate_email = request.POST.get('candidate_email')
            candidate_name = request.POST.get('candidate_name')
            subject = request.POST.get('subject')
            message = request.POST.get('message')
            
            if not all([candidate_email, candidate_name, subject, message]):
                logger.error("Missing required email fields")
                messages.error(request, 'All fields are required')
                return render(request, 'recruitment/send_email.html')
            
            send_custom_email(candidate_email, candidate_name, subject, message)
            logger.info(f"Custom email sent to {candidate_email}")
            messages.success(request, 'Email sent successfully')
            return redirect('send_custom_email')
        
        except Exception as e:
            logger.error(f"Error sending custom email: {str(e)}")
            messages.error(request, 'Failed to send email')
            return render(request, 'recruitment/send_email.html')
    
    return render(request, 'recruitment/send_email.html')

