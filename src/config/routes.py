class AppRoutes:
    """
    Define las rutas constantes de la aplicación para evitar 'Magic Strings'.
    Accesible por Router, Vistas y Servicios sin crear ciclos de importación.
    """
    LOGIN = "/login"
    DASHBOARD = "/dashboard"