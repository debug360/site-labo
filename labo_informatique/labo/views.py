import uuid
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
import re
import socket
import dns.resolver
from django.core.exceptions import ValidationError

from django.core.mail import send_mail
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
from django.conf import settings
from django.http import HttpResponseForbidden
from django.contrib import messages
from .forms import ContactForm  # Assurez-vous d'avoir défini ce formulaire
from django.db.models import Count
from .models import (
    Membre, Theme, Collaborateur, Devenir, Invitation, Presentation, 
    ImagePresentation, Categorie, Article, Temoignage, Evenement,Projet,HistoriqueTheme
)
from .utils import validate_email_domain,is_valid_email_domain
from .forms import (
    InvitationRegistrationForm, MembreProfileForm, PresentationForm, 
    ImagePresentationFormSet, ArticleForm, DevenirForm, ContactForm,
    InvitationForm, TemoignageForm, EvenementForm,MembreForm,UserCreateForm,ProjetForm,HistoriqueThemeForm  
)
import os


# Pages publiques
def home(request):
    """Page d'accueil du site."""
    # Récupérer les 3 derniers articles
    derniers_articles = Article.objects.filter(est_publie=True,statut_validation='valide').order_by('-date_creation')[:3]
    
    # Récupérer 3 membres aléatoires (non anciens)
    membres1 = Membre.objects.filter(est_responsable=True)
    membres = Membre.objects.filter(est_ancien=False , est_responsable=False).order_by('?')[:6]
    
    # Récupérer 3 témoignages aléatoires
    temoignages = Temoignage.objects.all().order_by('?')[:3]
    
    # Récupérer les événements à venir
    evenements = Evenement.objects.filter(date_debut__gte=timezone.now()).order_by('date_debut')[:3]
    
    # Statistiques
    nb_membres = Membre.objects.filter(est_ancien=False,est_responsable=True).count()
    nb_publications = Presentation.objects.count()
    nb_projets = Article.objects.filter(est_publie=True).count()  # Approximation
    nb_partenaires = Collaborateur.objects.count()
    # Récupérer 3 projets récents en cours
    projets_recents = Projet.objects.filter(
        est_public=True, 
        statut='en_cours'
    ).select_related('responsable', 'responsable__user').order_by('-date_creation')[:3]
    
    
    context = {
        'derniers_articles': derniers_articles,
        'membres1': membres1,
        'membres': membres,
        'temoignages': temoignages,
        'evenements': evenements,
        'nb_membres': nb_membres,
        'nb_publications': nb_publications,
        'nb_projets': nb_projets,
        'nb_partenaires': nb_partenaires,
        'projets_recents': projets_recents,
    }
    return render(request, 'core/home.html', context)


def about(request):
    """Page À propos du laboratoire."""
    nb_membres = Membre.objects.filter(est_ancien=False,est_responsable=True).count()
    nb_publications = Presentation.objects.count()
    nb_projets = Article.objects.filter(est_publie=True).count()  # Approximation
    nb_partenaires = Collaborateur.objects.count()
    nb_publication1=nb_publications+nb_projets
    context = {
        'nb_membres': nb_membres,
        'nb_publications': nb_publication1,
        'nb_projets': nb_projets,
        'nb_partenaires': nb_partenaires,
    }
    return render(request, 'core/about.html', context)
# 2. Fonctions de validation à utiliser dans la vue

def contact(request):
    """Page de contact avec vérification d'email."""
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            nom = form.cleaned_data['nom']
            email = form.cleaned_data['email']
            sujet = form.cleaned_data['sujet']
            message = form.cleaned_data['message']
            
            # La validation est déjà faite dans form.is_valid()
            # Si vous voulez une vérification supplémentaire:
            if not is_valid_email_domain(email):
                messages.error(request, "L'adresse email semble invalide. Veuillez vérifier.")
                return render(request, 'core/contact.html', {'form': form})
            
            # Envoyer l'email
            try:
                send_mail(
                    f'[Beta Lab] {sujet}',
                    f'Message de {nom} ({email}):\n\n{message}',
                    settings.DEFAULT_FROM_EMAIL,
                    [settings.CONTACT_EMAIL],
                    fail_silently=False,
                )
                
                messages.success(request, "Votre message a été envoyé avec succès ! Nous vous répondrons dans les plus brefs délais.")
                return redirect('labo:contact')
            except Exception as e:
                messages.error(request, f"Erreur lors de l'envoi de l'email: {str(e)}")
    else:
        form = ContactForm()
    
    context = {
        'form': form,
    }
    return render(request, 'core/contact.html', context)


def team(request):
   
    """Vue pour afficher tous les membres de l'équipe."""
    membres = Membre.objects.filter(est_ancien=False,est_responsable=False ).select_related('user', 'theme').prefetch_related(
        'historique_themes__theme'
    ).order_by('user__first_name', 'user__last_name')
     # Récupérer tous les thèmes pour les filtres
    themes = Theme.objects.all().order_by('nom')
    
    # ✅ Ajouter le thème actuel à chaque membre
    for membre in membres:
        membre.theme_actuel = membre.get_theme_actuel()
    
    context = {
        'membres': membres,
        'themes': themes,
    }
    
    return render(request, 'core/team.html', context)
def faq(request):
   
    return render(request, 'core/faq.html')

# Mise à jour de votre vue membre_detail dans views.py

def membre_detail(request, membre_id):
    """Vue pour afficher le détail d'un membre."""
    membre = get_object_or_404(
        Membre.objects.select_related('user', 'theme').prefetch_related(
            'historique_themes__theme'
        ),
        id=membre_id
    )
    
    # Récupérer les présentations du membre
    presentations = Presentation.objects.filter(
        membre=membre
    ).select_related('theme').order_by('-date_creation')[:5]
    
    # ✅ CORRECTION : Utiliser les champs de base de données au lieu de la méthode
    articles = Article.objects.filter(
        auteur=membre,
        est_publie=True,
        statut_validation='valide'  # Au lieu de est_visible_publiquement=True
    ).prefetch_related('categories').order_by('-date_creation')[:5]
    
    # Récupérer le parcours professionnel (pour les anciens)
    devenir = None
    if membre.est_ancien:
        try:
            devenir = Devenir.objects.get(membre=membre)
        except Devenir.DoesNotExist:
            pass
    
    # Récupérer l'historique des thèmes
    historique_themes = membre.get_historique_themes_complet()
    theme_actuel = membre.get_theme_actuel()
    duree_theme_actuel = membre.get_duree_theme_actuel()
    
    # Récupérer les projets du membre
    projets_responsable = membre.projets_responsable.filter(
        est_public=True
    ).order_by('-date_debut')[:3]
    
    projets_participant = membre.projets_participant.filter(
        est_public=True
    ).exclude(
        id__in=projets_responsable.values_list('id', flat=True)
    ).order_by('-date_debut')[:3]
    
    context = {
        'membre': membre,
        'presentations': presentations,
        'articles': articles,
        'devenir': devenir,
        'historique_themes': historique_themes,
        'theme_actuel': theme_actuel,
        'duree_theme_actuel': duree_theme_actuel,
        'projets_responsable': projets_responsable,
        'projets_participant': projets_participant,
    }
    
    return render(request, 'core/membre_detail.html', context)

def responsables(request):
    """Vue pour afficher les responsables et collaborateurs."""
    responsables = Membre.objects.filter(est_responsable=True).select_related('user', 'theme')
    collaborateurs = Collaborateur.objects.all().order_by('nom')
    
    context = {
        'responsables': responsables,
        'collaborateurs': collaborateurs,
    }
    return render(request, 'core/responsables.html', context)


def liste_presentations(request):
    """Vue pour afficher la liste des présentations."""
    presentations_list = Presentation.objects.all().select_related('membre', 'theme', 'membre__user').order_by('-date_creation')
    themes = Theme.objects.all()
    
    # Pagination
    paginator = Paginator(presentations_list, 9)  # 9 présentations par page
    page = request.GET.get('page')
    
    try:
        presentations = paginator.page(page)
    except PageNotAnInteger:
        presentations = paginator.page(1)
    except EmptyPage:
        presentations = paginator.page(paginator.num_pages)
    
    context = {
        'presentations': presentations,
        'themes': themes,
    }
    return render(request, 'core/liste_presentations.html', context)


def presentation_detail(request, presentation_id):
    """Vue pour afficher le détail d'une présentation."""
    presentation = get_object_or_404(
        Presentation.objects.select_related('membre', 'theme', 'membre__user'), 
        id=presentation_id
    )
    
    # Récupérer les images associées à la présentation
    images = ImagePresentation.objects.filter(presentation=presentation)
    
    # Récupérer d'autres présentations similaires (même thème, excluant celle-ci)
    related_presentations = Presentation.objects.filter(
        theme=presentation.theme
    ).exclude(
        id=presentation.id
    ).select_related('membre', 'membre__user').order_by('-date_creation')[:3]
    
    context = {
        'presentation': presentation,
        'images': images,
        'related_presentations': related_presentations,
    }
    return render(request, 'core/presentation_detail.html', context)


def liste_articles(request):
    """Vue pour afficher la liste des articles du blog."""
    articles_list = Article.objects.filter(est_publie=True,statut_validation='valide').select_related('auteur', 'auteur__user').order_by('-date_creation')
    categories = Categorie.objects.all()
    
    # Récupérer les articles récents pour le sidebar
    articles_recents = Article.objects.filter(est_publie=True,statut_validation='valide').order_by('-date_creation')[:5]
    
    # Récupérer les auteurs actifs
    auteurs = Membre.objects.filter(
        article__est_publie=True,
        article__statut_validation='valide'
    ).distinct().select_related('user')[:6]
    
    # Récupérer les thèmes pour le sidebar
    themes = Theme.objects.all()
    
    # Pagination
    paginator = Paginator(articles_list, 5)  # 5 articles par page
    page = request.GET.get('page')
    
    try:
        articles = paginator.page(page)
    except PageNotAnInteger:
        articles = paginator.page(1)
    except EmptyPage:
        articles = paginator.page(paginator.num_pages)
    
    context = {
        'articles': articles,
        'categories': categories,
        'articles_recents': articles_recents,
        'auteurs': auteurs,
        'themes': themes,
        'category': None,
    }
    return render(request, 'core/liste_articles.html', context)


def liste_articles_par_categorie(request, categorie_id):
    """Vue pour afficher les articles filtrés par catégorie."""
    categorie = get_object_or_404(Categorie, id=categorie_id)
    articles_list = Article.objects.filter(
        est_publie=True, 
        statut_validation='valide',
        categories=categorie
    ).select_related('auteur', 'auteur__user').order_by('-date_creation')
    
    categories = Categorie.objects.all()
    
    # Récupérer les articles récents pour le sidebar
    articles_recents = Article.objects.filter(est_publie=True).order_by('-date_creation')[:5]
    
    # Récupérer les auteurs actifs
    auteurs = Membre.objects.filter(
        article__est_publie=True
    ).distinct().select_related('user')[:6]
    
    # Récupérer les thèmes pour le sidebar
    themes = Theme.objects.all()
    
    # Pagination
    paginator = Paginator(articles_list, 5)  # 5 articles par page
    page = request.GET.get('page')
    
    try:
        articles = paginator.page(page)
    except PageNotAnInteger:
        articles = paginator.page(1)
    except EmptyPage:
        articles = paginator.page(paginator.num_pages)
    
    context = {
        'articles': articles,
        'categories': categories,
        'articles_recents': articles_recents,
        'auteurs': auteurs,
        'themes': themes,
        'category': categorie,
    }
    return render(request, 'core/liste_articles.html', context)


def liste_articles_par_theme(request, theme_id):
   """Vue pour afficher les articles filtrés par thème."""
   theme = get_object_or_404(Theme, id=theme_id)
   articles_list = Article.objects.filter(
       est_publie=True, 
       statut_validation='valide',
       auteur__theme=theme
   ).select_related('auteur', 'auteur__user').order_by('-date_creation')
   
   categories = Categorie.objects.all()
   
   # Récupérer les articles récents pour le sidebar
   articles_recents = Article.objects.filter(est_publie=True).order_by('-date_creation')[:5]
   
   # Récupérer les auteurs actifs
   auteurs = Membre.objects.filter(
       article__est_publie=True
   ).distinct().select_related('user')[:6]
   
   # Récupérer les thèmes pour le sidebar
   themes = Theme.objects.all()
   
   # Pagination
   paginator = Paginator(articles_list, 5)  # 5 articles par page
   page = request.GET.get('page')
   
   try:
       articles = paginator.page(page)
   except PageNotAnInteger:
       articles = paginator.page(1)
   except EmptyPage:
       articles = paginator.page(paginator.num_pages)
   
   context = {
       'articles': articles,
       'categories': categories,
       'articles_recents': articles_recents,
       'auteurs': auteurs,
       'themes': themes,
       'category': None,
       'theme': theme,
   }
   return render(request, 'core/liste_articles.html', context)


def article_detail(request, article_id):
   """Vue pour afficher le détail d'un article."""
   article = get_object_or_404(
       Article.objects.select_related('auteur', 'auteur__user'), 
       id=article_id,
       est_publie=True,
       statut_validation='valide'
   )
   
   # Récupérer les catégories de l'article
   categories = article.categories.all()
   
   # Récupérer tous les catégories pour le sidebar
   all_categories = Categorie.objects.all()
   
   # Récupérer les articles récents pour le sidebar
   articles_recents = Article.objects.filter(
       est_publie=True
   ).exclude(
       id=article.id
   ).order_by('-date_creation')[:5]
   
   # Récupérer les auteurs actifs
   auteurs = Membre.objects.filter(
       article__est_publie=True
   ).distinct().select_related('user')[:6]
   
   # Récupérer les articles similaires (même catégorie)
   related_articles = Article.objects.filter(
       est_publie=True,
       categories__in=categories
   ).exclude(
       id=article.id
   ).distinct().order_by('-date_creation')[:3]
   
   context = {
       'article': article,
       'categories': all_categories,
       'articles_recents': articles_recents,
       'auteurs': auteurs,
       'related_articles': related_articles,
   }
   return render(request, 'core/article_detail.html', context)

@login_required
def valider_article(request, article_id):
    """Valider un article."""
    # Vérifier que l'utilisateur est bien administrateur
    if not request.user.is_staff:
        return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
    
    article = get_object_or_404(Article, id=article_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        commentaire = request.POST.get('commentaire', '')
        
        if action == 'valider':
            article.statut_validation = 'valide'
            messages.success(request, f"L'article '{article.titre}' a été validé.")
        elif action == 'rejeter':
            article.statut_validation = 'rejete'
            messages.success(request, f"L'article '{article.titre}' a été rejeté.")
        
        article.date_validation = timezone.now()
        article.validateur = request.user
        article.commentaire_validation = commentaire
        article.save()
        
        # Optionnel : Envoyer un email à l'auteur
      # Optionnel : Envoyer un email à l'auteur
        try:
            subject = f"Statut de votre article '{article.titre}'"
            
            # Construire le message étape par étape pour éviter les conflits de guillemets
            statut_text = 'Validé' if action == 'valider' else 'Rejeté'
            commentaire_text = f"Commentaire de l'administrateur : {commentaire}" if commentaire else ""
            
            message = f"""Bonjour {article.auteur.user.first_name},

Le statut de votre article '{article.titre}' a été mis à jour.

Nouveau statut : {statut_text}

{commentaire_text}

Cordialement,
L'équipe Beta Lab
"""
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [article.auteur.user.email],
                fail_silently=True,
            )
        except:
            pass  # Ne pas faire échouer la validation si l'email ne part pas
    
    return redirect('labo:gestion_contenu', type_contenu='articles')

@login_required
def articles_en_attente(request):
    """Vue pour afficher les articles en attente de validation."""
    # Vérifier que l'utilisateur est bien administrateur
    if not request.user.is_staff:
        return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
    
    articles = Article.objects.filter(
        statut_validation='en_attente'
    ).select_related('auteur', 'auteur__user').order_by('-date_creation')
    
    context = {
        'articles': articles,
        'title': 'Articles en attente de validation',
    }
    return render(request, 'admin/articles_en_attente.html', context)

def devenir_membres(request):
   """Vue pour afficher le parcours des anciens membres."""
   devenirs = Devenir.objects.select_related('membre', 'membre__user').order_by('-membre__date_depart')
   
   # Récupérer tous les domaines uniques
   domaines = Devenir.objects.values_list('domaine', flat=True).distinct()
   
   # Récupérer toutes les années de départ uniques
   annees = Membre.objects.filter(est_ancien=True).dates('date_depart', 'year')
   annees = [date.year for date in annees]
   
   # Statistiques
   nb_membres = devenirs.count()
   nb_domaines = domaines.count()
   nb_lieux = Devenir.objects.values_list('lieu', flat=True).distinct().count()
   
   # Répartition par type de structure
   total = devenirs.count()
   nb_academique = devenirs.filter(type_structure='academique').count()
   nb_industrie = devenirs.filter(type_structure='industrie').count()
   nb_startup = devenirs.filter(type_structure='startup').count()
   
   pct_academique = int((nb_academique / total) * 100) if total > 0 else 0
   pct_industrie = int((nb_industrie / total) * 100) if total > 0 else 0
   pct_startup = int((nb_startup / total) * 100) if total > 0 else 0
   
   context = {
       'devenirs': devenirs,
       'domaines': domaines,
       'annees': annees,
       'nb_membres': nb_membres,
       'nb_domaines': nb_domaines,
       'nb_lieux': nb_lieux,
       'pct_academique': pct_academique,
       'pct_industrie': pct_industrie,
       'pct_startup': pct_startup,
   }
   return render(request, 'core/devenir_membres.html', context)


# Vues pour les utilisateurs authentifiés
@login_required
def dashboard(request):
   """Tableau de bord pour les membres connectés."""
   try:
       membre = Membre.objects.get(user=request.user)
   except Membre.DoesNotExist:
       messages.error(request, "Votre profil de membre n'a pas encore été configuré.")
       return redirect('labo:edit_profile')
   
   # Récupérer les présentations du membre
   presentations = Presentation.objects.filter(membre=membre).order_by('-date_creation')
   
   # Récupérer les articles du membre
   articles = Article.objects.filter(auteur=membre).order_by('-date_creation')
   
   # Si c'est un ancien membre, récupérer son parcours
   devenir = None
   if membre.est_ancien:
       devenir = Devenir.objects.filter(membre=membre).first()
   
   context = {
       'membre': membre,
       'presentations': presentations,
       'articles': articles,
       'devenir': devenir,
   }
   return render(request, 'membres/dashboard.html', context)


@login_required
def edit_profile(request):
   """Page d'édition du profil pour les membres."""
   try:
       membre = Membre.objects.get(user=request.user)
   except Membre.DoesNotExist:
       membre = None
   
   if request.method == 'POST':
       form = MembreProfileForm(request.POST, request.FILES, instance=membre)
       if form.is_valid():
           if membre is None:
               membre = form.save(commit=False)
               membre.user = request.user
               membre.date_arrivee = timezone.now().date()
               membre.save()
               messages.success(request, "Votre profil a été créé avec succès !")
           else:
               form.save()
               messages.success(request, "Votre profil a été mis à jour avec succès !")
           return redirect('labo:dashboard')
   else:
       form = MembreProfileForm(instance=membre)
   
   context = {
       'form': form,
       'is_new': membre is None,
   }
   return render(request, 'membres/edit_profil.html', context)


@login_required
def create_edit_presentation(request, presentation_id=None):
    """Création/édition d'une présentation."""
    try:
        membre = Membre.objects.get(user=request.user)
    except Membre.DoesNotExist:
        messages.error(request, "Vous devez d'abord compléter votre profil.")
        return redirect('labo:edit_profile')
    
    if presentation_id:
        presentation = get_object_or_404(Presentation, id=presentation_id)
        # Vérifier que le membre est bien l'auteur
        if presentation.membre != membre:
            return HttpResponseForbidden("Vous n'avez pas la permission de modifier cette présentation.")
    else:
        presentation = None
    
    if request.method == 'POST':
        form = PresentationForm(request.POST, request.FILES, instance=presentation)
        formset = ImagePresentationFormSet(request.POST, request.FILES, instance=presentation)
        
        if form.is_valid() and formset.is_valid():
            # D'abord sauvegarder la présentation
            presentation = form.save(commit=False)
            presentation.membre = membre
            presentation.save()
            form.save_m2m()  # Nécessaire si vous avez des relations ManyToMany
            
            # Maintenant lier le formset à la présentation et le sauvegarder
            formset.instance = presentation
            formset.save()
            
            if presentation_id:
                messages.success(request, "La présentation a été mise à jour avec succès !")
            else:
                messages.success(request, "La présentation a été créée avec succès !")
            
            return redirect('labo:presentation_detail', presentation_id=presentation.id)
    else:
        form = PresentationForm(instance=presentation)
        formset = ImagePresentationFormSet(instance=presentation)
    
    context = {
        'form': form,
        'formset': formset,
        'presentation': presentation,
    }
    return render(request, 'membres/edit_presentation.html', context)
@login_required
def create_edit_article(request, article_id=None):
   """Création/édition d'un article."""
   try:
       membre = Membre.objects.get(user=request.user)
   except Membre.DoesNotExist:
       messages.error(request, "Vous devez d'abord compléter votre profil.")
       return redirect('labo:edit_profile')
   
   if article_id:
       article = get_object_or_404(Article, id=article_id)
       # Vérifier que le membre est bien l'auteur
       if article.auteur != membre:
           return HttpResponseForbidden("Vous n'avez pas la permission de modifier cet article.")
   else:
       article = None
   
   if request.method == 'POST':
       form = ArticleForm(request.POST, request.FILES, instance=article)
       
       if form.is_valid():
           article = form.save(commit=False)
           article.auteur = membre
           article.save()
           # Pour les relations ManyToMany, il faut sauvegarder le formulaire après l'objet
           form.save_m2m()
           
           if article_id:
               messages.success(request, "L'article a été mis à jour avec succès !")
           else:
               messages.success(request, "L'article a été créé avec succès !")
           
           if article.est_publie:
               return redirect('labo:article_detail', article_id=article.id)
           else:
               return redirect('labo:dashboard')
   else:
       form = ArticleForm(instance=article)
   
   context = {
       'form': form,
       'article': article,
   }
   return render(request, 'membres/edit_article.html', context)

@login_required
def create_edit_devenir(request):
   """Création/édition du parcours post-laboratoire."""
   try:
       membre = Membre.objects.get(user=request.user)
   except Membre.DoesNotExist:
       messages.error(request, "Vous devez d'abord compléter votre profil.")
       return redirect('labo:edit_profile')
   
   # Vérifier que le membre est bien un ancien
   if not membre.est_ancien:
       messages.error(request, "Cette section est réservée aux anciens membres.")
       return redirect('labo:dashboard')
   
   try:
       devenir = Devenir.objects.get(membre=membre)
   except Devenir.DoesNotExist:
       devenir = None
   
   if request.method == 'POST':
       form = DevenirForm(request.POST, instance=devenir)
       
       if form.is_valid():
           devenir = form.save(commit=False)
           devenir.membre = membre
           devenir.save()
           
           messages.success(request, "Votre parcours a été mis à jour avec succès !")
           return redirect('labo:dashboard')
   else:
       form = DevenirForm(instance=devenir)
   
   context = {
       'form': form,
       'devenir': devenir,
   }
   return render(request, 'membres/edit_devenir.html', context)


# Vues pour l'administration
@login_required
def admin_dashboard(request):
   """Tableau de bord pour les administrateurs."""
   # Vérifier que l'utilisateur est bien administrateur
   if not request.user.is_staff:
       return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
   
   # Statistiques générales
   membres_count = Membre.objects.count()
   membres_actifs = Membre.objects.filter(est_ancien=False).count()
   anciens_membres = Membre.objects.filter(est_ancien=True).count()
   presentations_count = Presentation.objects.count()
   articles_count = Article.objects.count()
   articles_publies = Article.objects.filter(est_publie=True).count()
   
   # Activités récentes
   last_presentations = Presentation.objects.select_related('membre', 'membre__user').order_by('-date_creation')[:5]
   last_articles = Article.objects.select_related('auteur', 'auteur__user').order_by('-date_creation')[:5]
   last_signups = Membre.objects.select_related('user').order_by('-date_arrivee')[:5]
   
   context = {
       'membres_count': membres_count,
       'membres_actifs': membres_actifs,
       'anciens_membres': anciens_membres,
       'presentations_count': presentations_count,
       'articles_count': articles_count,
       'articles_publies': articles_publies,
       'last_presentations': last_presentations,
       'last_articles': last_articles,
       'last_signups': last_signups,
   }
   return render(request, 'admin/dashboard.html', context)


@login_required
def gestion_membres(request):
   """Gestion des membres pour les administrateurs."""
   # Vérifier que l'utilisateur est bien administrateur
   if not request.user.is_staff:
       return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
   
   membres = Membre.objects.select_related('user', 'theme').order_by('-date_arrivee')
   
   # Filtres
   est_responsable = request.GET.get('responsable')
   est_ancien = request.GET.get('ancien')
   theme_id = request.GET.get('theme')
   
   if est_responsable:
       membres = membres.filter(est_responsable=est_responsable == 'true')
   
   if est_ancien:
       membres = membres.filter(est_ancien=est_ancien == 'true')
   
   if theme_id:
       membres = membres.filter(theme_id=theme_id)
   
   # Liste des thèmes pour le filtre
   themes = Theme.objects.all()
   
   context = {
       'membres': membres,
       'themes': themes,
       'est_responsable': est_responsable,
       'est_ancien': est_ancien,
       'theme_id': theme_id,
   }
   return render(request, 'admin/gestion_membres.html', context)


@login_required
def edit_membre(request, membre_id):
   """Modification d'un membre par un administrateur."""
   # Vérifier que l'utilisateur est bien administrateur
   if not request.user.is_staff:
       return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
   
   membre = get_object_or_404(Membre, id=membre_id)
   user = membre.user
   
   if request.method == 'POST':
       # Mise à jour des champs utilisateur
       user.first_name = request.POST.get('first_name')
       user.last_name = request.POST.get('last_name')
       user.email = request.POST.get('email')
       user.save()
       
       # Mise à jour des champs membre
       membre.titre = request.POST.get('titre')
       membre.bio = request.POST.get('bio')
       
       theme_id = request.POST.get('theme')
       membre.theme = Theme.objects.get(id=theme_id) if theme_id else None
       
       membre.linkedin = request.POST.get('linkedin')
       membre.github = request.POST.get('github')
       membre.portfolio = request.POST.get('portfolio')
       
       membre.est_responsable = 'est_responsable' in request.POST
       membre.est_ancien = 'est_ancien' in request.POST
       
       membre.date_arrivee = request.POST.get('date_arrivee')
       if membre.est_ancien:
           membre.date_depart = request.POST.get('date_depart')
       
       if 'photo' in request.FILES:
           membre.photo = request.FILES['photo']
       
       membre.save()
       
       messages.success(request, "Le membre a été mis à jour avec succès !")
       return redirect('labo:gestion_membres')
   
   themes = Theme.objects.all()
   
   context = {
       'membre': membre,
       'themes': themes,
   }
   return render(request, 'admin/edit_membre.html', context)


@login_required
def gestion_invitations(request):
   """Gestion des invitations pour les administrateurs."""
   # Vérifier que l'utilisateur est bien administrateur
   if not request.user.is_staff:
       return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
   
   if request.method == 'POST':
       form = InvitationForm(request.POST)
       if form.is_valid():
           email = form.cleaned_data['email']
           message = form.cleaned_data['message']
           
           # Vérifier si l'email est déjà utilisé
           if User.objects.filter(email=email).exists():
               messages.error(request, f"L'email {email} est déjà associé à un utilisateur.")
               return redirect('labo:gestion_invitations')
           
           # Vérifier si une invitation active existe déjà pour cet email
           invitation = Invitation.objects.filter(
               email=email,
               is_used=False,
               expires_at__gt=timezone.now()
           ).first()
           
           if not invitation:
               # Créer un token unique
               token = uuid.uuid4().hex
               
               # Date d'expiration (30 jours)
               expires_at = timezone.now() + datetime.timedelta(days=30)
               
               # Créer l'invitation
               invitation = Invitation.objects.create(
                   email=email,
                   token=token,
                   expires_at=expires_at,
                   inviter=request.user
               )
           
           # Envoyer l'email d'invitation
           invitation_url = request.build_absolute_uri(
               f'/register/{invitation.token}/'
           )
           
           # Contenu de l'email
           subject = 'Invitation à rejoindre Beta Lab'
           email_body = f"Bonjour,\n\n"
           email_body += f"Vous avez été invité(e) à rejoindre la plateforme Beta Lab.\n\n"
           
           if message:
               email_body += f"Message de l'invitant : {message}\n\n"
           
           email_body += f"Pour créer votre compte, veuillez cliquer sur le lien suivant :\n"
           email_body += f"{invitation_url}\n\n"
           email_body += f"Ce lien est valable jusqu'au {invitation.expires_at.strftime('%d/%m/%Y')}.\n\n"
           email_body += f"Cordialement,\n"
           email_body += f"L'équipe Beta Lab"
           
           send_mail(
               subject,
               email_body,
               settings.DEFAULT_FROM_EMAIL,
               [email],
               fail_silently=False,
           )
           
           messages.success(request, f"Une invitation a été envoyée à {email}.")
           return redirect('labo:gestion_invitations')
   else:
       form = InvitationForm()
   
   # Liste des invitations
   invitations = Invitation.objects.select_related('inviter').order_by('-created_at')
   
   context = {
       'form': form,
       'invitations': invitations,
   }
   return render(request, 'admin/gestion_invitations.html', context)


@login_required
def resend_invitation(request, invitation_id):
   """Renvoyer une invitation."""
   # Vérifier que l'utilisateur est bien administrateur
   if not request.user.is_staff:
       return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
   
   invitation = get_object_or_404(Invitation, id=invitation_id)
   
   # Mettre à jour la date d'expiration
   invitation.expires_at = timezone.now() + datetime.timedelta(days=30)
   invitation.save()
   
   # Envoyer l'email d'invitation
   invitation_url = request.build_absolute_uri(
       f'/register/{invitation.token}/'
   )
   
   # Contenu de l'email
   subject = 'Invitation à rejoindre Beta Lab (rappel)'
   email_body = f"Bonjour,\n\n"
   email_body += f"Vous avez été invité(e) à rejoindre la plateforme Beta Lab.\n\n"
   email_body += f"Pour créer votre compte, veuillez cliquer sur le lien suivant :\n"
   email_body += f"{invitation_url}\n\n"
   email_body += f"Ce lien est valable jusqu'au {invitation.expires_at.strftime('%d/%m/%Y')}.\n\n"
   email_body += f"Cordialement,\n"
   email_body += f"L'équipe Beta Lab"
   
   send_mail(
       subject,
       email_body,
       settings.DEFAULT_FROM_EMAIL,
       [invitation.email],
       fail_silently=False,
   )
   
   messages.success(request, f"L'invitation a été renvoyée à {invitation.email}.")
   return redirect('labo:gestion_invitations')


@login_required
def cancel_invitation(request, invitation_id):
   """Annuler une invitation."""
   # Vérifier que l'utilisateur est bien administrateur
   if not request.user.is_staff:
       return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
   
   invitation = get_object_or_404(Invitation, id=invitation_id)
   email = invitation.email
   invitation.delete()
   
   messages.success(request, f"L'invitation pour {email} a été annulée.")
   return redirect('labo:gestion_invitations')
# views.py
@login_required
def delete_membres(request, membre_id):
   """Suppression d'un membre."""
   # Vérifier que l'utilisateur est bien administrateur
   if not request.user.is_staff:
       return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
   
   membre = get_object_or_404(Membre, id=membre_id)
   membre.delete()
   
   messages.success(request, "Le membre a été supprimée.")
   if request.user.is_staff:
        return redirect('labo:gestion_membres')
   else:
        return redirect('labo:admin_dashboard')

@login_required
def create_membre(request):
    """Vue pour créer un nouveau membre directement par l'administrateur."""
    # Vérifier que l'utilisateur est admin
    if not request.user.is_staff:
        return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
    
    themes = Theme.objects.all()
    
    if request.method == 'POST':
        # Création d'un nouvel utilisateur
        username = request.POST.get('username', '')
        password = User.objects.make_random_password()
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        email = request.POST.get('email', '')
        
        # Validation de base
        if not username or not email or not first_name or not last_name:
            messages.error(request, "Tous les champs obligatoires doivent être remplis.")
            return render(request, 'admin/create_membre.html', {'themes': themes})
        
        # Vérifier si l'utilisateur existe déjà
        if User.objects.filter(username=username).exists():
            messages.error(request, f"Le nom d'utilisateur '{username}' est déjà utilisé.")
            return render(request, 'admin/create_membre.html', {'themes': themes})
        
        if User.objects.filter(email=email).exists():
            messages.error(request, f"L'adresse email '{email}' est déjà utilisée.")
            return render(request, 'admin/create_membre.html', {'themes': themes})
        
        # Créer l'utilisateur
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        
        # Créer le profil membre
        membre = Membre()
        membre.user = user
        membre.titre = request.POST.get('titre', '')
        
        theme_id = request.POST.get('theme', '')
        if theme_id:
            membre.theme = get_object_or_404(Theme, pk=theme_id)
        
        membre.bio = request.POST.get('bio', '')
        membre.linkedin = request.POST.get('linkedin', '')
        membre.github = request.POST.get('github', '')
        membre.portfolio = request.POST.get('portfolio', '')
        membre.est_responsable = 'est_responsable' in request.POST
        membre.est_ancien = 'est_ancien' in request.POST
        
        # Nouveau champ statut_ancien
        if membre.est_ancien:
            membre.statut_ancien = request.POST.get('statut_ancien', '')
        
        date_arrivee = request.POST.get('date_arrivee', '')
        if date_arrivee:
            membre.date_arrivee = date_arrivee
        
        # Date de départ seulement si l'ancien membre a quitté le laboratoire
        if membre.est_ancien and membre.statut_ancien == 'parti':
            date_depart = request.POST.get('date_depart', '')
            if date_depart:
                membre.date_depart = date_depart
        
        # Gestion de la photo
        if 'photo' in request.FILES:
            membre.photo = request.FILES['photo']
            
        membre.save()
        
        # Envoi d'un email avec les informations de connexion
        try:
            subject = 'Bienvenue sur Beta Lab - Vos informations de connexion'
            message = f"""Bonjour {first_name},

Votre compte a été créé sur la plateforme Beta Lab.

Voici vos informations de connexion :
- Nom d'utilisateur : {username}
- Mot de passe temporaire : {password}

Nous vous recommandons de changer votre mot de passe après votre première connexion.

Cordialement,
L'équipe Beta Lab
"""
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
            messages.success(request, f"Le membre {first_name} {last_name} a été créé avec succès. Un email a été envoyé avec les informations de connexion.")
        except Exception as e:
            messages.warning(request, f"Le membre a été créé, mais l'email n'a pas pu être envoyé. Identifiants : {username} / {password}")
        
        return redirect('labo:gestion_membres')
    
    return render(request, 'admin/create_membre.html', {'themes': themes})

@login_required
def gestion_collaborateurs(request):
   """Gestion des collaborateurs pour les administrateurs."""
   # Vérifier que l'utilisateur est bien administrateur
   if not request.user.is_staff:
       return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
   
   collaborateurs = Collaborateur.objects.all().order_by('nom')
   
   context = {
       'collaborateurs': collaborateurs,
   }
   return render(request, 'admin/gestion_collaborateurs.html', context)


@login_required
def create_edit_collaborateur(request, collaborateur_id=None):
   """Création/édition d'un collaborateur."""
   # Vérifier que l'utilisateur est bien administrateur
   if not request.user.is_staff:
       return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
   
   if collaborateur_id:
       collaborateur = get_object_or_404(Collaborateur, id=collaborateur_id)
   else:
       collaborateur = None
   
   if request.method == 'POST':
       # Récupérer les données
       prenom = request.POST.get('prenom')
       nom = request.POST.get('nom')
       titre = request.POST.get('titre')
       institution = request.POST.get('institution')
       description = request.POST.get('description')
       email = request.POST.get('email')
       lien = request.POST.get('lien')
       
       if collaborateur:
           # Mettre à jour le collaborateur existant
           collaborateur.prenom = prenom
           collaborateur.nom = nom
           collaborateur.titre = titre
           collaborateur.institution = institution
           collaborateur.description = description
           collaborateur.email = email
           collaborateur.lien = lien
       else:
           # Créer un nouveau collaborateur
           collaborateur = Collaborateur(
               prenom=prenom,
               nom=nom,
               titre=titre,
               institution=institution,
               description=description,
               email=email,
               lien=lien
           )
       
       # Gérer la photo
       if 'photo' in request.FILES:
           collaborateur.photo = request.FILES['photo']
       
       collaborateur.save()
       
       if collaborateur_id:
           messages.success(request, "Le collaborateur a été mis à jour avec succès !")
       else:
           messages.success(request, "Le collaborateur a été créé avec succès !")
       
       return redirect('labo:gestion_collaborateurs')
   
   context = {
       'collaborateur': collaborateur,
   }
   return render(request, 'admin/edit_collaborateur.html', context)


@login_required
def delete_collaborateur(request, collaborateur_id):
   """Suppression d'un collaborateur."""
   # Vérifier que l'utilisateur est bien administrateur
   if not request.user.is_staff:
       return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
   
   collaborateur = get_object_or_404(Collaborateur, id=collaborateur_id)
   nom = f"{collaborateur.prenom} {collaborateur.nom}"
   collaborateur.delete()
   
   messages.success(request, f"Le collaborateur {nom} a été supprimé.")
   return redirect('labo:gestion_collaborateurs')


@login_required
def gestion_contenu(request, type_contenu='articles'):
   """Gestion du contenu pour les administrateurs."""
   # Vérifier que l'utilisateur est bien administrateur
   if not request.user.is_staff:
       return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
   
   # Gestion des différents types de contenu
   articles_en_attente_count = 0
   if type_contenu == 'articles':
       items = Article.objects.select_related('auteur', 'auteur__user').order_by('-date_creation')
       title = "Gestion des articles"
       articles_en_attente_count = Article.objects.filter(statut_validation='en_attente').count()
    
       context = {
            'items': items,
            'type_contenu': type_contenu,
            'title': title,
            'articles_en_attente_count': articles_en_attente_count,
       }
       return render(request, 'admin/gestion_contenu.html', context)
   elif type_contenu == 'presentations':
       items = Presentation.objects.select_related('membre', 'membre__user', 'theme').order_by('-date_creation')
       title = "Gestion des présentations"
   elif type_contenu == 'temoignages':
       items = Temoignage.objects.all().order_by('-date')
       title = "Gestion des témoignages"
   elif type_contenu == 'evenements':
       items = Evenement.objects.all().order_by('-date_debut')
       title = "Gestion des événements"
   else:
       messages.error(request, "Type de contenu non reconnu.")
       return redirect('labo:admin_dashboard')
   
   context = {
       'items': items,
       'type_contenu': type_contenu,
       'title': title,
   }
   return render(request, 'admin/gestion_contenu.html', context)


@login_required
def create_edit_temoignage(request, temoignage_id=None):
   """Création/édition d'un témoignage."""
   # Vérifier que l'utilisateur est bien administrateur
   if not request.user.is_staff:
       return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
   
   if temoignage_id:
       temoignage = get_object_or_404(Temoignage, id=temoignage_id)
   else:
       temoignage = None
   
   if request.method == 'POST':
       form = TemoignageForm(request.POST, request.FILES, instance=temoignage)
       
       if form.is_valid():
           form.save()
           
           if temoignage_id:
               messages.success(request, "Le témoignage a été mis à jour avec succès !")
           else:
               messages.success(request, "Le témoignage a été créé avec succès !")
           
           return redirect('labo:gestion_contenu', type_contenu='temoignages')
   else:
       form = TemoignageForm(instance=temoignage)
   
   context = {
       'form': form,
       'temoignage': temoignage,
   }
   return render(request, 'admin/edit_temoignage.html', context)


@login_required
def delete_temoignage(request, temoignage_id):
   """Suppression d'un témoignage."""
   # Vérifier que l'utilisateur est bien administrateur
   if not request.user.is_staff:
       return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
   
   temoignage = get_object_or_404(Temoignage, id=temoignage_id)
   temoignage.delete()
   
   messages.success(request, "Le témoignage a été supprimé.")
   return redirect('labo:gestion_contenu', type_contenu='temoignages')


@login_required
def create_edit_evenement(request, evenement_id=None):
   """Création/édition d'un événement."""
   # Vérifier que l'utilisateur est bien administrateur
   if not request.user.is_staff:
       return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
   
   if evenement_id:
       evenement = get_object_or_404(Evenement, id=evenement_id)
   else:
       evenement = None
   
   if request.method == 'POST':
       form = EvenementForm(request.POST, request.FILES, instance=evenement)
       
       if form.is_valid():
           form.save()
           
           if evenement_id:
               messages.success(request, "L'événement a été mis à jour avec succès !")
           else:
               messages.success(request, "L'événement a été créé avec succès !")
           
           return redirect('labo:gestion_contenu', type_contenu='evenements')
   else:
       form = EvenementForm(instance=evenement)
   
   context = {
       'form': form,
       'evenement': evenement,
   }
   return render(request, 'admin/edit_evenement.html', context)


@login_required
def delete_evenement(request, evenement_id):
   """Suppression d'un événement."""
   # Vérifier que l'utilisateur est bien administrateur
   if not request.user.is_staff:
       return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
   
   evenement = get_object_or_404(Evenement, id=evenement_id)
   evenement.delete()
   
   messages.success(request, "L'événement a été supprimé.")
   return redirect('labo:gestion_contenu', type_contenu='evenements')


# Fonctions d'authentification
def register_with_invitation(request, token):
   """Inscription avec une invitation."""
   # Vérifier que le token est valide
   invitation = get_object_or_404(
       Invitation, 
       token=token, 
       is_used=False, 
       expires_at__gt=timezone.now()
   )
   
   if request.method == 'POST':
       form = InvitationRegistrationForm(request.POST)
       form.fields['email'].initial = invitation.email
       
       if form.is_valid():
           user = form.save()
           
           # Marquer l'invitation comme utilisée
           invitation.is_used = True
           invitation.save()
           
           # Connecter l'utilisateur
           login(request, user)
           
           messages.success(request, "Votre compte a été créé avec succès ! Complétez maintenant votre profil.")
           return redirect('labo:edit_profile')
   else:
       form = InvitationRegistrationForm()
       form.fields['email'].initial = invitation.email
   
   context = {
       'form': form,
       'invitation': invitation,
   }
   return render(request, 'auth/register.html', context)


@login_required
def gestion_themes(request):
    """Vue pour gérer les thèmes de recherche."""
    # Vérifier que l'utilisateur est admin
    if not request.user.is_staff:
        return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
    
    # Récupérer tous les thèmes
    themes = Theme.objects.all().order_by('nom')
    
    context = {
        'themes': themes,
    }
    return render(request, 'admin/gestion_themes.html', context)

@login_required
def save_theme(request):
    """Vue pour créer ou mettre à jour un thème."""
    # Vérifier que l'utilisateur est admin
    if not request.user.is_staff:
        return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
    
    if request.method == 'POST':
        theme_id = request.POST.get('theme_id', '')
        nom = request.POST.get('nom', '').strip()
        description = request.POST.get('description', '').strip()
        
        # Validation
        if not nom:
            messages.error(request, "Le nom du thème est obligatoire.")
            return redirect('labo:gestion_themes')
        
        # Vérifier si on modifie ou crée un thème
        if theme_id:
            # Modification d'un thème existant
            try:
                theme = Theme.objects.get(pk=theme_id)
                theme.nom = nom
                theme.description = description
                theme.save()
                messages.success(request, f"Le thème '{nom}' a été modifié avec succès.")
            except Theme.DoesNotExist:
                messages.error(request, "Le thème que vous essayez de modifier n'existe pas.")
        else:
            # Création d'un nouveau thème
            # Vérifier si un thème avec ce nom existe déjà
            if Theme.objects.filter(nom=nom).exists():
                messages.error(request, f"Un thème avec le nom '{nom}' existe déjà.")
            else:
                Theme.objects.create(nom=nom, description=description)
                messages.success(request, f"Le thème '{nom}' a été créé avec succès.")
    
    return redirect('labo:gestion_themes')

@login_required
def delete_theme(request):
    """Vue pour supprimer un thème."""
    # Vérifier que l'utilisateur est admin
    if not request.user.is_staff:
        return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
    
    if request.method == 'POST':
        theme_id = request.POST.get('theme_id', '')
        
        if theme_id:
            try:
                theme = Theme.objects.get(pk=theme_id)
                
                # Vérifier si des membres sont associés à ce thème
                if theme.membre_set.count() > 0:
                    messages.error(request, f"Impossible de supprimer le thème '{theme.nom}' car des membres y sont associés.")
                else:
                    nom = theme.nom
                    theme.delete()
                    messages.success(request, f"Le thème '{nom}' a été supprimé avec succès.")
            except Theme.DoesNotExist:
                messages.error(request, "Le thème que vous essayez de supprimer n'existe pas.")
    
    return redirect('labo:gestion_themes')
# views.py
@login_required
def create_edit_theme(request, theme_id=None):
    """Vue pour créer ou modifier un thème."""
    # Vérifier que l'utilisateur est admin
    if not request.user.is_staff:
        return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
    
    # Si theme_id est fourni, on modifie un thème existant
    theme = None
    if theme_id:
        theme = get_object_or_404(Theme, pk=theme_id)
    
    if request.method == 'POST':
        nom = request.POST.get('nom', '').strip()
        description = request.POST.get('description', '').strip()
        
        # Validation
        if not nom:
            messages.error(request, "Le nom du thème est obligatoire.")
            return render(request, 'admin/edit_theme.html', {'theme': theme})
        
        # Vérifier si on modifie ou crée un thème
        if theme:
            # Modification d'un thème existant
            theme.nom = nom
            theme.description = description
            theme.save()
            messages.success(request, f"Le thème '{nom}' a été modifié avec succès.")
        else:
            # Création d'un nouveau thème
            # Vérifier si un thème avec ce nom existe déjà
            if Theme.objects.filter(nom=nom).exists():
                messages.error(request, f"Un thème avec le nom '{nom}' existe déjà.")
                return render(request, 'admin/edit_theme.html', {'theme': None})
            
            Theme.objects.create(nom=nom, description=description)
            messages.success(request, f"Le thème '{nom}' a été créé avec succès.")
        
        return redirect('labo:gestion_themes')
    
    # Afficher le formulaire (GET)
    return render(request, 'admin/edit_theme.html', {'theme': theme})

# Vues pour la gestion des catégories d'articles

@login_required
def gestion_categories(request):
    """Vue pour gérer les catégories d'articles."""
    # Vérifier que l'utilisateur est admin
    if not request.user.is_staff:
        return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
    
    # Récupérer toutes les catégories
    categories = Categorie.objects.all().order_by('nom')
    
    context = {
        'categories': categories,
    }
    return render(request, 'admin/gestion_categories.html', context)

@login_required
def create_edit_categorie(request, categorie_id=None):
    """Vue pour créer ou modifier une catégorie."""
    # Vérifier que l'utilisateur est admin
    if not request.user.is_staff:
        return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
    
    # Si categorie_id est fourni, on modifie une catégorie existante
    categorie = None
    if categorie_id:
        categorie = get_object_or_404(Categorie, pk=categorie_id)
    
    if request.method == 'POST':
        nom = request.POST.get('nom', '').strip()
        description = request.POST.get('description', '').strip()
        
        # Validation
        if not nom:
            messages.error(request, "Le nom de la catégorie est obligatoire.")
            return render(request, 'admin/edit_categorie.html', {'categorie': categorie})
        
        # Vérifier si on modifie ou crée une catégorie
        if categorie:
            # Modification d'une catégorie existante
            categorie.nom = nom
            categorie.description = description
            categorie.save()
            messages.success(request, f"La catégorie '{nom}' a été modifiée avec succès.")
        else:
            # Création d'une nouvelle catégorie
            # Vérifier si une catégorie avec ce nom existe déjà
            if Categorie.objects.filter(nom=nom).exists():
                messages.error(request, f"Une catégorie avec le nom '{nom}' existe déjà.")
                return render(request, 'admin/edit_categorie.html', {'categorie': None})
            
            Categorie.objects.create(nom=nom, description=description)
            messages.success(request, f"La catégorie '{nom}' a été créée avec succès.")
        
        return redirect('labo:gestion_categories')
    
    # Afficher le formulaire (GET)
    return render(request, 'admin/edit_categorie.html', {'categorie': categorie})

@login_required
def delete_categorie(request):
    """Vue pour supprimer une catégorie."""
    # Vérifier que l'utilisateur est admin
    if not request.user.is_staff:
        return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
    
    if request.method == 'POST':
        categorie_id = request.POST.get('categorie_id', '')
        
        if categorie_id:
            try:
                categorie = Categorie.objects.get(pk=categorie_id)
                
                # Vérifier si des articles sont associés à cette catégorie
                if categorie.article_set.exists():
                    messages.error(request, f"Impossible de supprimer la catégorie '{categorie.nom}' car des articles y sont associés.")
                else:
                    nom = categorie.nom
                    categorie.delete()
                    messages.success(request, f"La catégorie '{nom}' a été supprimée avec succès.")
            except Categorie.DoesNotExist:
                messages.error(request, "La catégorie que vous essayez de supprimer n'existe pas.")
    
    return redirect('labo:gestion_categories')

@login_required
def delete_presentation(request, presentation_id):
   """Suppression d'une présentation."""
   # Vérifier que l'utilisateur est bien administrateur
   if not request.user.is_staff:
       return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
   
   presentation = get_object_or_404(Presentation, id=presentation_id)
   presentation.delete()
   
   messages.success(request, "La présentation a été supprimée.")
   if request.user.is_staff:
        return redirect('labo:gestion_contenu', type_contenu='presentations')
   else:
        return redirect('labo:dashboard')

@login_required
def delete_article(request, article_id):
   """Suppression d'un article."""
   # Vérifier que l'utilisateur est bien administrateur
   if not request.user.is_staff:
       return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
   
   article = get_object_or_404(Article, id=article_id)
   article.delete()
   
   messages.success(request, "L'article a été supprimé.")
   if request.user.is_staff:
        return redirect('labo:gestion_contenu', type_contenu='articles')
   else:
        return redirect('labo:dashboard')



def liste_projets(request):
    """Vue pour afficher la liste des projets."""
    # Filtres
    statut_filtre = request.GET.get('statut', '')
    type_filtre = request.GET.get('type', '')
    
    projets_list = Projet.objects.filter(est_public=True).select_related(
        'responsable', 'responsable__user'
    ).prefetch_related('participants', 'collaborateurs_externes')
    
    # Appliquer les filtres
    if statut_filtre:
        projets_list = projets_list.filter(statut=statut_filtre)
    if type_filtre:
        projets_list = projets_list.filter(type_projet=type_filtre)
    
    # Séparer projets en cours et terminés
    projets_en_cours = projets_list.filter(statut='en_cours')
    projets_termines = projets_list.filter(statut='termine')
    autres_projets = projets_list.exclude(statut__in=['en_cours', 'termine'])
    
    # Récupérer les options de filtre
    statuts = Projet.STATUT_CHOICES
    types = Projet.TYPE_CHOICES
    
    # Statistiques
    nb_projets_total = projets_list.count()
    nb_projets_en_cours = projets_en_cours.count()
    nb_projets_termines = projets_termines.count()
    
    context = {
        'projets_en_cours': projets_en_cours,
        'projets_termines': projets_termines,
        'autres_projets': autres_projets,
        'statuts': statuts,
        'types': types,
        'statut_filtre': statut_filtre,
        'type_filtre': type_filtre,
        'nb_projets_total': nb_projets_total,
        'nb_projets_en_cours': nb_projets_en_cours,
        'nb_projets_termines': nb_projets_termines,
    }
    return render(request, 'core/liste_projets.html', context)


def projet_detail(request, projet_id):
    """Vue pour afficher le détail d'un projet."""
    projet = get_object_or_404(
        Projet.objects.select_related('responsable', 'responsable__user').prefetch_related(
            'participants', 'participants__user', 'collaborateurs_externes'
        ),
        id=projet_id,
        est_public=True
    )
    
    # Récupérer les projets similaires (même type, excluant celui-ci)
    projets_similaires = Projet.objects.filter(
        type_projet=projet.type_projet,
        est_public=True
    ).exclude(
        id=projet.id
    ).select_related('responsable', 'responsable__user')[:3]
    
    context = {
        'projet': projet,
        'projets_similaires': projets_similaires,
    }
    return render(request, 'core/projet_detail.html', context)


# Vues d'administration
@login_required
def gestion_projets(request):
    """Gestion des projets pour les administrateurs."""
    if not request.user.is_staff:
        return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
    
    projets = Projet.objects.select_related(
        'responsable', 'responsable__user'
    ).order_by('-date_creation')
    
    # Statistiques
    nb_projets = projets.count()
    nb_en_cours = projets.filter(statut='en_cours').count()
    nb_termines = projets.filter(statut='termine').count()
    
    context = {
        'projets': projets,
        'nb_projets': nb_projets,
        'nb_en_cours': nb_en_cours,
        'nb_termines': nb_termines,
    }
    return render(request, 'admin/gestion_projets.html', context)


@login_required
def create_edit_projet(request, projet_id=None):
    """Création/édition d'un projet."""
    if not request.user.is_staff:
        return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
    
    if projet_id:
        projet = get_object_or_404(Projet, id=projet_id)
    else:
        projet = None
    
    if request.method == 'POST':
        form = ProjetForm(request.POST, request.FILES, instance=projet)
        
        if form.is_valid():
            projet = form.save()
            
            if projet_id:
                messages.success(request, "Le projet a été mis à jour avec succès !")
            else:
                messages.success(request, "Le projet a été créé avec succès !")
            
            return redirect('labo:gestion_projets')
    else:
        form = ProjetForm(instance=projet)
    
    context = {
        'form': form,
        'projet': projet,
    }
    return render(request, 'admin/edit_projet.html', context)


@login_required
def delete_projet(request, projet_id):
    """Suppression d'un projet."""
    if not request.user.is_staff:
        return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
    
    projet = get_object_or_404(Projet, id=projet_id)
    titre = projet.titre
    projet.delete()
    
    messages.success(request, f"Le projet '{titre}' a été supprimé.")
    return redirect('labo:gestion_projets')


@login_required
def gestion_historique_themes(request):
    """Vue d'administration pour gérer les historiques de thèmes."""
    if not request.user.is_staff:
        return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
    
    # Filtres
    membre_id = request.GET.get('membre', '')
    theme_id = request.GET.get('theme', '')
    
    # Requête de base
    historiques = HistoriqueTheme.objects.select_related(
        'membre__user', 'theme'
    ).order_by('-date_debut')
    
    # Appliquer les filtres
    if membre_id:
        historiques = historiques.filter(membre_id=membre_id)
    if theme_id:
        historiques = historiques.filter(theme_id=theme_id)
    
    # Pour les filtres
    membres = Membre.objects.select_related('user').order_by('user__first_name', 'user__last_name')
    themes = Theme.objects.all().order_by('nom')
    
    # Statistiques
    nb_total = HistoriqueTheme.objects.count()
    nb_actuels = HistoriqueTheme.objects.filter(date_fin__isnull=True).count()
    nb_membres_avec_historique = Membre.objects.filter(historique_themes__isnull=False).distinct().count()
    
    context = {
        'historiques': historiques,
        'membres': membres,
        'themes': themes,
        'membre_id': int(membre_id) if membre_id.isdigit() else None,
        'theme_id': int(theme_id) if theme_id.isdigit() else None,
        'nb_total': nb_total,
        'nb_actuels': nb_actuels,
        'nb_membres_avec_historique': nb_membres_avec_historique,
    }
    
    return render(request, 'admin/gestion_historique_themes.html', context)

@login_required
def create_edit_historique_theme(request, membre_id=None, historique_id=None):
    """Vue pour créer/éditer un historique de thème."""
    if not request.user.is_staff:
        return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
    
    if historique_id:
        # Mode édition
        historique = get_object_or_404(HistoriqueTheme, id=historique_id)
        membre = historique.membre
    elif membre_id and membre_id != 0:
        # Mode création pour un membre spécifique
        membre = get_object_or_404(Membre, id=membre_id)
        historique = None
    else:
        # Mode création général
        membre = None
        historique = None
    
    if request.method == 'POST':
        print(f"POST reçu : {request.POST}")  # Debug
        form = HistoriqueThemeForm(request.POST, instance=historique, membre=membre)
        
        print(f"Formulaire valide : {form.is_valid()}")  # Debug
        if not form.is_valid():
            print(f"Erreurs formulaire : {form.errors}")  # Debug
        
        if form.is_valid():
            try:
                historique = form.save()
                print(f"Historique sauvé : {historique}")  # Debug
                
                if historique_id:
                    messages.success(request, "L'historique de thème a été mis à jour avec succès.")
                else:
                    messages.success(request, f"Historique de thème créé pour {historique.membre}.")
                
                return redirect('labo:gestion_historique_themes')
            except Exception as e:
                print(f"Erreur lors de la sauvegarde : {e}")  # Debug
                messages.error(request, f"Erreur lors de la sauvegarde : {e}")
        else:
            # Afficher les erreurs
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = HistoriqueThemeForm(instance=historique, membre=membre)
    
    context = {
        'form': form,
        'historique': historique,
        'membre': membre,
    }
    
    return render(request, 'admin/edit_historique_theme.html', context)

@login_required
def delete_historique_theme(request, historique_id):
    """Vue pour supprimer un historique de thème."""
    if not request.user.is_staff:
        return HttpResponseForbidden("Vous n'avez pas les droits administrateur.")
    
    historique = get_object_or_404(HistoriqueTheme, id=historique_id)
    
    if request.method == 'POST':
        membre_nom = str(historique.membre)
        theme_nom = historique.theme.nom
        historique.delete()
        
        messages.success(request, f"Historique de thème supprimé : {membre_nom} - {theme_nom}")
        return redirect('labo:gestion_historique_themes')
    
    context = {
        'historique': historique,
    }
    
    return render(request, 'admin/confirm_delete_historique.html', context)
