from rest_framework.views import APIView
from submission.models import SubmissionClass, SubmissionCompetition
from .serializers import PathSerializer, SubmissionClassSerializer, SumissionClassListSerializer, SubmissionCompetitionSerializer, SumissionCompetitionListSerializer
from competition.models import CompetitionUser
from rest_framework.pagination import PageNumberPagination #pagination
from utils.pagination import PaginationHandlerMixin #pagination
from utils.evaluation import EvaluationMixin
from utils.get_ip import GetIpAddr
from utils.get_obj import *
from utils.message import *
from utils.common import IP_ADDR
from django.db.models import Q
from rest_framework.response import Response
from rest_framework import status
import uuid
import mimetypes
import os
import urllib
from django.http import HttpResponse
from django.utils import timezone

# submission-class 관련
class SubmissionClassView(APIView, EvaluationMixin):

    # 05-16
    def post(self, request, class_id, contest_id, cp_id):
        class_ = get_class(class_id)
        contest = get_contest(contest_id)
        contest_problem = get_contest_problem(cp_id)

        if (contest_problem.contest_id.id != contest_id) or (contest_problem.contest_id.class_id.id != class_id):
            return Response(msg_error_id, status=status.HTTP_400_BAD_REQUEST)

        time_check = timezone.now()
        if (contest.start_time > time_check) or (contest.end_time < time_check):
            return Response(msg_time_error, status=status.HTTP_400_BAD_REQUEST)

        data = request.data.copy()
        
        csv_str = data['csv'].name.split('.')[-1]
        ipynb_str = data['ipynb'].name.split('.')[-1]
        if csv_str != 'csv':
            return Response(msg_SubmissionClassView_post_e_1, status=status.HTTP_400_BAD_REQUEST)
        if ipynb_str != 'ipynb':
            return Response(msg_SubmissionClassView_post_e_2, status=status.HTTP_400_BAD_REQUEST)


        temp = str(uuid.uuid4()).replace("-","")

        path_json = {
            "path": temp
        }

        submission_json = {
            "username": request.user,
            "class_id": contest_problem.contest_id.class_id.id,
            "contest_id": contest_problem.contest_id.id,
            "c_p_id": contest_problem.id,
            "csv": data['csv'],
            "ipynb": data['ipynb'],
            "problem_id": contest_problem.problem_id.id,
            "score": None,
            "ip_address": GetIpAddr(request)
        }

        path_serializer = PathSerializer(data=path_json)
        if path_serializer.is_valid():
            path_obj = path_serializer.save()
            submission_json['path'] = path_obj.id
            submission_serializer = SubmissionClassSerializer(data=submission_json)

            if submission_serializer.is_valid():
                submission = submission_serializer.save()
                # evaluation
                problem = get_problem(submission.problem_id.id)
                self.evaluate(submission=submission, problem=problem)
                
                return Response(msg_success, status=status.HTTP_200_OK)
            else:
                return Response(submission_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(path_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class BasicPagination(PageNumberPagination):
    page_size_query_param = 'limit'

class SubmissionClassListView(APIView, PaginationHandlerMixin):
    # pagination
    pagination_class = BasicPagination

    # 07-00 유저 submission 내역 조회
    def get(self, request):
        cp_id = request.GET.get('cpid', 0)
        contest_problem = get_contest_problem(cp_id)
        submission_class_list = SubmissionClass.objects.all().filter(username=request.user).filter(c_p_id=cp_id).order_by('-created_time')

        obj_list = []

        for submission in submission_class_list:
            csv_url = "http://{0}/api/submissions/class/{1}/download/csv".format(IP_ADDR, submission.id)
            ipynb_url = "http://{0}/api/submissions/class/{1}/download/ipynb".format(IP_ADDR, submission.id)
            
            obj = {
                "id": submission.id,
                "username": submission.username,
                "score": submission.score,
                "csv": csv_url,
                "ipynb": ipynb_url,
                "created_time": submission.created_time,
                "status": submission.status,
                "on_leaderboard": submission.on_leaderboard
            }
            obj_list.append(obj)

        page = self.paginate_queryset(obj_list)
        if page is not None:
            serializer = self.get_paginated_response(SumissionClassListSerializer(page, many=True).data)
        else:
            serializer = SumissionClassListSerializer(obj_list, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class SubmissionClassCheckView(APIView):
    # 05-17
    def patch(self, request, class_id, contest_id, cp_id):
        class_ = get_class(class_id)
        contest = get_contest(contest_id)
        contest_problem = get_contest_problem(cp_id)

        data = request.data
        class_submission = get_submission_class(data['id'])

        if class_submission.username.username != request.user.username:
            return Response(msg_SubmissionCheckView_patch_e_1, status=status.HTTP_400_BAD_REQUEST)

        # on_leaderboard를 모두 False로 설정
        submission_list = SubmissionClass.objects.filter(username = request.user.username).filter(c_p_id=cp_id)
        for submission in submission_list:
            submission.on_leaderboard = False
            submission.save()
        
        # submission의 on_leaderboard를 True로 설정
        class_submission.on_leaderboard = True
        class_submission.save()

        return Response(msg_success, status=status.HTTP_200_OK)


# submission-competition 관련
class SubmissionCompetitionView(APIView, EvaluationMixin):

    # 06-04 대회 유저 파일 제출
    def post(self, request, competition_id):
        competition = get_competition(competition_id)
        # permission check - 대회에 참가한 학생만 제출 가능

        time_check = timezone.now()
        if (competition.start_time > time_check) or (competition.end_time < time_check):
            return Response(msg_time_error, status=status.HTTP_400_BAD_REQUEST)

        user = get_username(request.user.username)
        if CompetitionUser.objects.filter(username = request.user.username).filter(competition_id = competition_id).count() == 0:
            return Response({'error':"대회에 참가하지 않았습니다."}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data.copy()

        csv_str = data['csv'].name.split('.')[-1]
        ipynb_str = data['ipynb'].name.split('.')[-1]
        if csv_str != 'csv':
            return Response(msg_SubmissionClassView_post_e_1, status=status.HTTP_400_BAD_REQUEST)
        if ipynb_str != 'ipynb':
            return Response(msg_SubmissionClassView_post_e_2, status=status.HTTP_400_BAD_REQUEST)

        temp = str(uuid.uuid4()).replace("-","")
        path_json = {
            "path":temp
        }

        submission_json = {
            "username" : request.user,
            "competition_id" : competition.id,
            "csv" : data["csv"],
            "ipynb" : data["ipynb"],
            "problem_id" : competition.problem_id.id,
            "score" : None,
            "ip_address" : GetIpAddr(request)
        }

        path_serializer = PathSerializer(data=path_json)
        if path_serializer.is_valid():
            path_obj = path_serializer.save()
            submission_json["path"] = path_obj.id
            submission_serializer = SubmissionCompetitionSerializer(data=submission_json)
            if submission_serializer.is_valid():
                submission = submission_serializer.save()
                # evaluation
                problem = get_problem(submission.problem_id.id)
                self.evaluate(submission=submission, problem=problem)
                
                return Response(msg_success, status=status.HTTP_200_OK)
            else:
                return Response(submission_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(path_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class SubmissionCompetitionListView(APIView, PaginationHandlerMixin):

    # pagination
    pagination_class = BasicPagination

    # 06-07 유저 submission 내역 조회
    def get(self, request, competition_id):
        competition = get_competition(competition_id)
        username = request.GET.get('username', '')
        
        submission_comptition_list = SubmissionCompetition.objects.filter(competition_id = competition_id)
        if username:
            submission_comptition_list = submission_comptition_list.filter(username=username)
        
        obj_list = []
         
        for submission in submission_comptition_list:
            csv_url = "http://{0}/api/submissions/competition/{1}/download/csv".format(IP_ADDR, submission.id)
            ipynb_url = "http://{0}/api/submissions/competition/{1}/download/ipynb".format(IP_ADDR, submission.id)

            obj = {
                "id": submission.id,
                "username": submission.username,
                "score": submission.score,
                "csv": csv_url,
                "ipynb": ipynb_url,
                "created_time": submission.created_time,
                "status": submission.status,
                "on_leaderboard": submission.on_leaderboard
            }
            obj_list.append(obj)

        page = self.paginate_queryset(obj_list)
        if page is not None:
            serializer = self.get_paginated_response(SumissionCompetitionListSerializer(page, many=True).data)
        else:
            serializer = SumissionCompetitionListSerializer(obj_list, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class SubmissionCompetitionCheckView(APIView):

    # 06-06 submission 리더보드 체크
    def patch(self, request, competition_id):
        competition = get_competition(competition_id)

        data = request.data
        competition_submission = get_submission_competition(id=data["id"])

        if competition_submission.username.username != request.user.username:
            return Response(msg_SubmissionCheckView_patch_e_1, status=status.HTTP_400_BAD_REQUEST)

        # on_leaderboard를 모두 False로 설정
        submission_list = SubmissionCompetition.objects.filter(username = request.user.username).filter(competition_id=competition.id)

        for submission in submission_list:
            submission.on_leaderboard = False
            submission.save()

        # submission의 on_leaderboard를 True로 설정
        competition_submission.on_leaderboard = True
        competition_submission.save()

        return Response(msg_success, status=status.HTTP_200_OK)

    

class SubmissionClassCsvDownloadView(APIView):
    # permission_classes = [IsAuthenticated]

    def get(self, request, submission_id):
        submission = get_submission_class(submission_id)

        # Define Django project base directory
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # result = /Users/ingyu/Desktop/BE/problem
        BASE_DIR = BASE_DIR.replace("/submission", "")

        csv_path = str(submission.csv.path).split('uploads/', 1)[1]
        filename = csv_path.split('/', 2)[2]
        filename = urllib.parse.quote(filename.encode('utf-8'))
        filepath = BASE_DIR + '/uploads/' + csv_path

        # Open the file for reading content
        path = open(filepath, 'r')
        # Set the mime type
        mime_type, _ = mimetypes.guess_type(filepath)
        response = HttpResponse(path, content_type=mime_type)
        # Set the HTTP header for sending to browser
        response['Content-Disposition'] = 'attachment; filename*=UTF-8\'\'%s' % filename
        return response

class SubmissionClassIpynbDownloadView(APIView):
    # permission_classes = [IsAuthenticated]

    def get(self, request, submission_id):
        submission = get_submission_class(submission_id)

        # Define Django project base directory
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # result = /Users/ingyu/Desktop/BE/problem
        BASE_DIR = BASE_DIR.replace("/submission", "")

        csv_path = str(submission.ipynb.path).split('uploads/', 1)[1]
        filename = csv_path.split('/', 2)[2]
        filename = urllib.parse.quote(filename.encode('utf-8'))
        filepath = BASE_DIR + '/uploads/' + csv_path
        
        # Open the file for reading content
        path = open(filepath, 'r')
        # Set the mime type
        mime_type, _ = mimetypes.guess_type(filepath)
        response = HttpResponse(path, content_type=mime_type)
        # Set the HTTP header for sending to browser
        response['Content-Disposition'] = 'attachment; filename*=UTF-8\'\'%s' % filename
        return response

class SubmissionCompetitionCsvDownloadView(APIView):
    # permission_classes = [IsAuthenticated]

    def get(self, request, submission_id):
        submission = get_submission_competition(submission_id)

        # Define Django project base directory
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # result = /Users/ingyu/Desktop/BE/problem
        BASE_DIR = BASE_DIR.replace("/submission", "")

        csv_path = str(submission.csv.path).split('uploads/', 1)[1]
        filename = csv_path.split('/', 2)[2]
        filename = urllib.parse.quote(filename.encode('utf-8'))
        filepath = BASE_DIR + '/uploads/' + csv_path

        # Open the file for reading content
        path = open(filepath, 'r')
        # Set the mime type
        mime_type, _ = mimetypes.guess_type(filepath)
        response = HttpResponse(path, content_type=mime_type)
        # Set the HTTP header for sending to browser
        response['Content-Disposition'] = 'attachment; filename*=UTF-8\'\'%s' % filename
        return response

class SubmissionCompetitionIpynbDownloadView(APIView):
    # permission_classes = [IsAuthenticated]

    def get(self, request, submission_id):
        submission = get_submission_competition(submission_id)

        # Define Django project base directory
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # result = /Users/ingyu/Desktop/BE/problem
        BASE_DIR = BASE_DIR.replace("/submission", "")

        csv_path = str(submission.ipynb.path).split('uploads/', 1)[1]
        filename = csv_path.split('/', 2)[2]
        filename = urllib.parse.quote(filename.encode('utf-8'))
        filepath = BASE_DIR + '/uploads/' + csv_path
        
        # Open the file for reading content
        path = open(filepath, 'r')
        # Set the mime type
        mime_type, _ = mimetypes.guess_type(filepath)
        response = HttpResponse(path, content_type=mime_type)
        # Set the HTTP header for sending to browser
        response['Content-Disposition'] = 'attachment; filename*=UTF-8\'\'%s' % filename
        return response