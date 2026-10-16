"""
URL configuration for chinese_site project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from lessons import views as lesson_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', lesson_views.home, name='home'),
    path('progress/', lesson_views.progress, name='progress'),
    path('journal/', lesson_views.journal_list, name='journal-list'),
    path('journal/new/', lesson_views.journal_save, name='journal-create'),
    path('journal/<int:pk>/', lesson_views.journal_detail, name='journal-detail'),
    path('journal/<int:pk>/edit/', lesson_views.journal_save, name='journal-edit'),
    path('lessons/', lesson_views.lesson_list, name='lesson-list'),
    path('words/', lesson_views.word_list, name='word-list'),
    path('practice/', lesson_views.practice, name='practice'),
    path('words/sync-anki/', lesson_views.word_sync_anki, name='word-sync-anki'),
    path('words/export.csv', lesson_views.word_export, name='word-export'),
    path('sources/new/', lesson_views.source_create, name='source-create'),
    path('lessons/new/', lesson_views.lesson_create, name='lesson-create'),
]
