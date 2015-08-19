import os
import logging

logger = logging.getLogger('datapyp.utils')

def str_2_bool(bool_str):
    """
    Case independent function to convert a string representation of a 
    boolean (``'true'``/``'false'``, ``'yes'``/``'no'``) into a ``bool``. This is case 
    insensitive, and will also accept part of a boolean string 
    (``'t'``/``'f'``, ``'y'``/``'n'``).
    
    Raises a :py:class:`astromatic.utils.pipeline.PipelineError` 
    if an invalid expression is entered.
    
    Parameters
    ----------
    bool_str: str
        String to convert to a boolean
    """
    lower_str = bool_str.lower()
    if 'true'.startswith(lower_str) or 'yes'.startswith(lower_str):
        return True
    elif 'false'.startswith(lower_str) or 'no'.startswith(lower_str):
        return False
    else:
        raise PipelineError(
            "'{0}' did not match a boolean expression "
            " (true/false, yes/no, t/f, y/n)".format(bool_str))

def get_bool(prompt):
    """
    Prompt a user for a boolean expression and repeat until a valid boolean
    has been entered.
    
    Parameters
    ----------
    prompt: str
        The text to prompt the user with.
    """
    try:
        bool_str = str_2_bool(raw_input(prompt))
    except PipelineError:
        logger.warn(
            "'{0}' did not match a boolean expression "
            "(true/false, yes/no, t/f, y/n)".format(bool_str))
        return get_bool(prompt)
    return bool_str

def create_paths(paths):
    """                                                                         
    Search for paths on the server. If a path does not exist, create the necessary directories.
    For example, if ``paths=['~/Documents/images/2014-6-5_data/']`` and only the path 
    *'~/Documents'* exists, both *'~/Documents/images/'* and 
    *'~/Documents/images/2014-6-5_data/'* are created.
    
    Parameters
    ----------
    paths: str or list of strings
        If paths is a string, this is the path to search for and create. 
        If paths is a list, each one is a path to search for and create
    """
    from astropy.extern.six import string_types
    if isinstance(paths, string_types):
        paths=[paths]
    for path in paths:
        try:
            os.makedirs(path)
        except OSError:
            if not os.path.isdir(path):
                raise PipelineError("Problem creating new directory, check user permissions")

def check_path(path, auto_create=False):
    """
    Check if a path exists and if it doesn't, give the user the option to create it.
    
    Parameters
    ----------
    path: str
        Name of the path to check
    auto_create: bool (optional)
        If the path does not exist and ``auto_create==True``, the path will 
        automatically be created, otherwise the user will be prompted to create the path
    """
    if not os.path.exists(path):
        if auto_create or get_bool("'{0}' does not exist, create (y/n)?".format(path)):
            create_paths(path)
        else:
            raise PipelineError("{0} does not exist".format(path))