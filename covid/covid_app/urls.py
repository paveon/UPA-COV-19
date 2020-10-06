from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "covid_app"

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='covid_app:dashboard', permanent=False)),
    path('index/', views.IndexView.as_view(), name='index'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),

    # path('clear_db/', views.clear_db, name='clear_db'),

    # path('index/', views.GamesView.as_view(), name='index'),
    # path('login/', views.LoginView.as_view(), name='login'),
    # path('logout/', views.logout_view, name='logout'),
    # path('signup/', views.SignupView.as_view(), name='signup'),
    # path('genre/<slug:slug>/', views.GenreDetailView.as_view(), name='genre_detail'),
    # path('player/<slug:slug>/', views.PlayerDetailView.as_view(), name='player_detail'),
    # path('team/<slug:slug>/', views.TeamDetailView.as_view(), name='team_detail'),
    # path('clan/<slug:slug>/', views.ClanDetailView.as_view(), name='clan_detail'),
    # path('game/<slug:slug>/', views.GameDetailView.as_view(), name='game_detail'),
    # path('match/<pk>/', views.MatchDetailView.as_view(), name='match_detail'),
    # path('games/', views.GamesView.as_view(), name='games'),
    # path('social/', views.SocialView.as_view(), name='social'),
    # path('settings/', views.SettingsView.as_view(), name='settings'),
    # path('tournaments/', views.TournamentView.as_view(), name='tournaments'),
    # path('tournament/<slug:slug>/', views.TournamentDetailView.as_view(), name='tournament_detail'),
    # path('gamemode/<slug:slug>/', views.GameModeDetailView.as_view(), name='game_mode_detail')
]