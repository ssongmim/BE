from rest_framework.views import APIView
from .models import Exam
from .serializer import ExamSerializer, ExamGenerateSerializer
from rest_framework.generics import get_object_or_404
from django.http import Http404, HttpResponse
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from utils.pagination import PaginationHandlerMixin
from contest.models import Contest


class BasicPagination(PageNumberPagination):
    page_size_query_param = 'limit'


class ExamParticipateView(APIView, PaginationHandlerMixin):
    pagination_class = BasicPagination

    def get_object(self, contest_id, user_id):
        try:
            exam = Exam.objects.get(contest=contest_id, user=user_id)
        except:
            exam = Http404
        return exam

    def get(self, request, class_id, contest_id):


        exams = Exam.objects.filter(contest=contest_id)
        page = self.paginate_queryset(exams)
        if page is not None:
            serializer = self.get_paginated_response(ExamSerializer(page, many=True).data)
        else:
            serializer = ExamSerializer(exams, many=True)
        return Response(serializer.data)

    def post(self, request, contest_id, class_id):
        # 권한 체크
        try:
            if request.user.class_user_set.get(class_id=class_id).privilege == 0:
                message = {"error": "해당 class의 교수 또는 TA가 아닙니다."}
                return Response(data=message, status=status.HTTP_400_BAD_REQUEST)
            else:
                pass
        except:
            message = {"error": "해당 class에 속하지 않습니다."}
            return Response(data=message, status=status.HTTP_400_BAD_REQUEST)

        contest = Contest.objects.get(id=contest_id)

        if not contest.is_exam:
            message = {"error": "해당 contest는 시험이 아닙니다"}
            return Response(data=message, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        data['user'] = request.user.id
        data['contest'] = contest.id

        exam = self.get_object(contest_id=contest_id, user_id=request.user.id)

        # 기존 ip제출 내역이 없다면
        # ip중복체크 후 중복된것이 없다면 새로 만들고, 중복이라면 거절한다.
        if exam == Http404:

            try:
                exams = Exam.objects.filter(ip_address=data['ip_address'])
            except Exam.DoesNotExist:
                exams = None

            if exams:
                message = {"error": "ip중복 입니다."}
                return Response(data=message, status=status.HTTP_400_BAD_REQUEST)
            else:

                serializer = ExamGenerateSerializer(data=data)
                if serializer.is_valid():
                    serializer.save()
                    return Response(data=serializer.data)
                else:
                    return Response(serializer.errors)
        else:
            if exam.exception:
                exam.exception = False
                serializer = ExamGenerateSerializer(exam, data=data)
                if serializer.is_valid():

                    serializer.save()
                    return Response(data=serializer.data)
                else:
                    return Response(serializer.errors)
            else:
                message = {"error": "이미 제출된 내역이 있습니다."}
                return Response(data=message, status=status.HTTP_400_BAD_REQUEST)
        message = {"error": "처리해야합니다"}
        return Response(data=message)


class ExamExceptionView(APIView):

    def get_object(self, exam_id):
        exam = get_object_or_404(Exam, id=exam_id)
        return exam

    def post(self, request, class_id, contest_id, exam_id):
        exam = self.get_object(exam_id)
        if exam == Http404:
            message = {'error': '해당하는 제출 내역이 없습니다.'}
            return Response(data=message, status=status.HTTP_400_BAD_REQUEST)
        else:
            exam.exception = True
            exam.save()
            return Response(data=ExamSerializer(exam).data, status=status.HTTP_200_OK)


class ExamResetView(APIView):

    def get_object(self, exam_id):
        exam = get_object_or_404(Exam, id=exam_id)
        return exam

    def post(self, request, class_id, contest_id, exam_id):
        exam = self.get_object(exam_id)
        if exam == Http404:
            message = {'error': '해당하는 제출 내역이 없습니다.'}
            return Response(data=message, status=status.HTTP_400_BAD_REQUEST)
        else:
            exam.delete()
            message = {'success': '해당 사용자의 제출 내역이 리셋되었습니다.'}
            return Response(data=message, status=status.HTTP_200_OK)