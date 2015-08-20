# Copyright 2015 Fred Moolekamp
# BSD 3-clause license
"""
Class and functions to define an astronomy pipeline
"""
import os
import subprocess
import copy
import logging
import warnings

logger = logging.getLogger('datapyp.core')

class PipelineError(Exception):
    """
    Errors generated by running Pipeline
    """
    pass

def load_pipeline(path):
    """
    Load a pipeline from a filename. This attempts to use the fastest method (cPickle)
    and if that fails it tries dill, then finally pickle. If all three fail an error
    is returned.
    
    Parameters
    ----------
    path: str
        Filename of pipeline to load
    """
    try:
        # Fastest
        import cPickle
        p = cPickle.load(open(path, 'rb'))
        logger.debug('loaded pipeline with cPickle')
        return p
    except:
        try:
            # Most broad
            import dill
            p = dill.load(open(path, 'rb'))
            logger.debug('loaded pipeline with dill')
            return p
        except ImportError:
            # Unlikely to work if the others failed, but still try
            import pickle
            p = pickle.load(open(path, 'rb'))
            logger.debug('loaded pipeline with pickle')
            return p
    
    raise PipelineError("Unable to load pipeline with cPickle, dill, or pickle")

def run_step(params):
    """
    Run a specified step in a pipeline
    
    Parameters
    ----------
    
    """
    step, func_kwargs, run_step_idx, ignore_errors, ignore_exceptions = params
    
    logger.debug('function kwargs: {0}'.format(step.func_kwargs))
    
    # Attempt to run the step. If an exception occurs, use the
    # ignore_exceptions parameter to determine whether to 
    # stop the Pipeline's execution or warn the user and
    # continue
    if (ignore_exceptions is not None and ignore_exceptions) or (
            ignore_exceptions is None and step.ignore_exceptions):
        try:
            result = step.func(**func_kwargs)
        except Exception as error:
            import traceback
            warning_str = "Exception occurred during step {0} (run_step_idx {1})".format(
                step.step_id, run_step_idx)
            warnings.warn(warning_str)
            result = {
                'status': 'error', 
                'error': traceback.format_exc()
            }
    else:
        result = step.func(**func_kwargs)
    
    step.results = result
    # Check that the result is a dictionary with a 'status' key
    if result is None or not isinstance(result, dict) or 'status' not in result:
        warning_str = "Step {0} (run_step_idx {1}) did not return a valid result".format(
            step.step_id, run_step_idx)
        warnings.warn(warning_str)
        result = {
            'status': 'unknown',
            'result': result
        }
    # If there was an error in the step, use ignore_errors to determine whether
    # or not to raise an exception
    if result['status'].lower() == 'error':
        if ((ignore_errors is None and not step.ignore_errors) or
                not ignore_errors):
            raise PipelineError(
                'Error returned in step {0} (run_step_idx {1})'.format(
                    step.step_id, run_step_idx
                ))
        else:
            warning_str = "Error in step {0} (run_step_idx{1})".format(
                step.step_id, run_step_idx)
            warning_str += ", see results for more"
            warnings.warn(warning_str)
    return step

class StepContainer:
    def get_next_id(self):
        next_id = self.next_id
        self.next_id += 1
        return next_id
    
    def add_step(self, func, tags=list(), ignore_errors=False, ignore_exceptions=False, **kwargs):
        """
        Build a new `PipelineStep` to the pipeline
    
        Parameters
        ----------
        func: function
            A function to be run in the pipeline. All functions must return
            a dictionary with (at a minimum) a ``status`` key whose value is either
            ``success`` or ``error``. It is also common to return a ``warnings`` key whose
            value is an astropy table that contains a list of warnings that may have
            occured during the step. The entire result dictionary returned from the function
            is saved in the pipeline's log file.
        tags: list (optional)
            A list of tags used to identify the step. When running the pipeline the user
            can specify a set of conditions that will filter which steps are run (or not run)
            based on a set of specified tags
        ignore_errors: bool (optional)
            If ``ignore_errors==False`` the pipeline will raise an exception if an error
            occurred during this step in the pipeline (meaning it returned a result with
            ``result['status']=='error'``). The default is ``False``.
        ignore_exceptions: bool (optional)
            If ``ignore_exceptions==True`` the pipeline will set ``result['status']=='error'``
            for the step that threw an exception and continue running. The default is
            ``ignore_exceptions==False``, which will stop the pipeline and raise an
            exception.
        kwargs: dict
            Keyword arguments passed to the ``func`` when the pipeline is run
        """
        if isinstance(func, PipelineStep) or isinstance(func, MultiprocessStep):
            if func.step_id is None:
                func.step_id = self.get_next_id()
            self.steps.append(func)
        else:
            step_id = self.get_next_id()
            self.steps.append(PipelineStep(
                func,
                step_id,
                tags,
                ignore_errors,
                ignore_exceptions,
                kwargs
            ))

class Pipeline(StepContainer):
    def __init__(self, paths={}, pipeline_name=None,
            next_id=0, create_paths=False, **kwargs):
        """
        Parameters
        ----------
        paths: dict (optional)
            Paths used for files generated by the pipeline. Each key will be
            added to the ``Pipeline`` class as the name of a path, and its
            corresponding value is the path to be used. If ``create_paths==True``,
            the path will automatically be created on the disk if it does not
            exist, otherwise the user will be asked whether or not to create the path.
            At a minimum it is recommended to define a ``temp_path``, used to
            store temporary files generated by the pipeline and a ``log_path``,
            used to save any log files created by the pipeline and the pipeline itself
            after each step.
        pipeline_name: str (optional)
            Name of the pipeline (used when saving the pipeline). The default
            value is ``None``, which results in the current date being used
            for the pipeline name in the form
            'year-month-day_hours-minutes-seconds'.
        steps: list of `astromatic.utils.pipeline.PipelineStep` (optional)
            If the user already has a list of steps to run they can be 
            set when the pipeline is initialized
        next_id: int (optional)
            Next number to use for a pipeline step id. The default is ``0``
        create_paths: bool (optional)
            If ``create_paths==True``, any path in ``paths`` that does not exist
            is created. Otherwise the user will be prompted if a path does not
            exist. The default is to prompt the user (``create_paths==False``).
        kwargs: dict
            Additional keyword arguments that might be used in a custom pipeline.
        """
        from datapyp.utils import check_path
        from types import MethodType
        self.create_paths = create_paths
        self.name = pipeline_name
        self.steps = []
        self.next_id = next_id
        self.run_steps = None
        self.run_warnings = None
        self.run_step_idx = 0
        self.paths = paths
        
        # Set additional keyword arguements
        for key, value in kwargs.items():
            setattr(self, key, value)
        # Set pipeline global variables
        if 'global_vars' not in kwargs:
            kwargs['global_vars'] = {}
        self.global_vars = PipelineGlobals(**kwargs['global_vars'])
        # If the pipeline doesn't have a name, use the current time
        if self.name is None:
            import datetime
            self.name = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S_pipeline')
        # Create (or prompt user to create) any specified paths that do not exist
        # and add them to the class members
        for path_name, path in self.paths.items():
            check_path(path, self.create_paths)
        # Warn the user if any of the recommended paths do not exist
        if 'temp' not in self.paths:
            warnings.warn(
                "'temp' path has not been set for the pipeline. "
                "If this pipeline generates temporary files an error may occur")
        if 'log' not in self.paths:
            warnings.warn(
                "'log' path has not been set for the pipeline. Log files will not be saved.")
    
    def save_pipeline(self, logfile, dump_type=None):
        """
        Save the pipeline to file
        
        Parameters
        ----------
        dump_type: str (optional)
            Module to use to dump the pipeline. If no dump_type is specified the function
            will first try cPickle, then pickle, then dill
        log_exception: bool (optional)
            If the pipeline cannot be saved, if ``log_exception==True`` an exception
            will be raised.
        
        Returns
        -------
        success: bool
            If the file was saved the function returns ``True``
        """
        # Depending on the contents of the pipeline cPickle might work
        if dump_type=='pickle' or dump_type is None:
            try:
                import cPickle
                cPickle.dump(self, open(logfile, 'wb'))
                dump_type = 'pickle'
                logger.debug('saved using cPickle')
                return True
            except:
                try:
                    import pickle
                    pickle.dump(self, open(logfile, 'wb'))
                    dump_type = 'pickle'
                    logger.debug('saved using pickle')
                    return True
                except:
                    if dump_type=='pickle':
                        warnings.warn(
                            'Pipeline is not picklable. If dill is installed try '
                            'setting dump_type to "dill" or None')
        # If pickle didn't work or the user specified dill use dill serialization
        if dump_type=='dill' or dump_type is None:
            try:
                import dill
                dill.dump(self, open(logfile, 'wb'))
                dump_type = 'dill'
                logger.debug('saved using dill')
                return True
            except ImportError:
                if dump_type is None:
                    warnings.warn(
                        'Pipeline could not be saved with pickle. Try installing '
                        'the "dill" module from pip')
                else:
                    warnings.warn('Pipeline could not be saved with dill')
            except:
                warnings.warn('Pipeline could not be saved with dill')
        warnings.warn('Pipeline not saved')
        return False
    
    def get_func_kwargs(self, step):
        """
        Add on any special keywords to the function kwargs
        """
        import inspect
        func_kwargs = step.func_kwargs.copy()

        # Some functions use step_id to keep track of log files, so the id of
        # the current step is added to the funciton call
        function_args = inspect.getargspec(step.func).args
        if 'step_id' in function_args:
            func_kwargs['step_id'] = step.step_id
        
        # Include the pipelines global variables
        if 'global_vars' in function_args:
            func_kwargs['global_vars'] = self.global_vars
        
        # Some functions require the Pipeline as a parameter,
        # so pass the pipeline to the function
        if 'pipeline' in function_args:
            func_kwargs['pipeline'] = self
        return func_kwargs
    
    def run(self, run_tags=[], ignore_tags=[], run_steps=None, run_name=None,
            resume=False, ignore_errors=None, ignore_exceptions=None,
            start_idx=None, current_step_idx=None, dump_type=None,
            log_exception=False):
        """
        Run the pipeline given a list of PipelineSteps
        
        Parameters
        ----------
        run_tags: list (optional)
            Run all steps that have a tag listed in ``run_tags`` and not in ``ignore_tags``.
            If ``len(run_tags)==0`` then all of the steps are run that are not listed 
            in ignore tags.
        ignore_tags: list (optional)
            Ignore all steps that contain one of the tags in ``ignore_tags``.
        run_steps: list of `PipelineStep` (optional)
            Instead of running the steps associated with a pipeline, the user can specify
            a set of steps to run. This can be useful if (for example) mulitple criteria
            are used to select steps to run and the user wants to perform these cuts in
            some other function to generate the necessary steps to run.
        run_name: str (optional)
            Name of the current run. When a pipeline is run, if a ``logpath`` has been
            specified then a copy of the pipline with a record of all warnings and
            steps run is saved in the ``logpath`` directory. A ``run_name`` can be specified
            to distinguish between different runs of the same pipeline with the same
            ``logpath``.
        resume: bool (optional)
            If ``resume==True`` and ``start_idx is None``, the pipeline will continue
            where it left off. If ``resume==False`` and ``start_idx is None`` then the
            pipeline will start at the first step (Pipeline.run_step_idx=0). The
            default is ``resume=False``.
        ignore_errors: bool (optional)
            If ``ignore_errors==False`` the pipeline will raise an exception if an error
            occurred during any step in the pipeline which returned a result with
            ``result['status']=='error'``. The default is ``None``, which will use
            the ``ignore_errors`` parameter for each individual step to decide whether
            or not to throw an exception.
        ignore_exceptions: bool (optional)
            If ``ignore_exceptions==True`` the pipeline will set ``result['status']=='error'``
            for the step that threw an exception and continue running. The default is ``None``, 
            which will use the ``ignore_exception`` parameter for each individual step to 
            decide whether or not to throw an exception.
        start_idx: int (optional)
            Index of ``Pipeline.run_steps`` to begin running the pipeline. All steps in 
            ``Pipeline.run_steps`` after ``start_idx`` will be run in order. The default
            value is ``None``, which will not change the current ``Pipeline.run_step_idx``.
        dump_type: str (optional)
            Module to use to dump the pipeline. If no dump_type is specified the function
            will first try cPickle, then pickle, then dill
        log_exception: bool (optional)
            If the pipeline cannot be saved, if ``log_exception==True`` an exception
            will be raised.
        """
        # If no steps are specified and the user is not resuming a previous run,
        # run all of the steps associated with the pipeline
        if run_steps is not None:
            self.run_steps = run_steps
        elif  self.run_steps is None or not resume:
            self.run_steps = [step for step in self.steps]
        # Filter the steps based on run_tags and ignore_tags, with ignore tags 
        # taking precendent
        self.run_steps = [step for step in self.run_steps if
            (len(run_tags) == 0 or any([tag in run_tags for tag in step.tags])) and
            not any([tag in ignore_tags for tag in step.tags])]
        
        # Set the path of the log file for the current run
        skip_save = True
        if 'log' in self.paths:
            if run_name is None:
                logfile = os.path.join(self.paths['log'], 'pipeline.p')
            else:
                logfile = os.path.join(self.paths['log'], 'pipeline-{0}.p'.format(run_name))
            logger.info('Pipeline state will be saved to {0}'.format(logfile))
            
            if self.save_pipeline(logfile, dump_type):
                skip_save = False
            elif log_exception:
                raise PipelineError("Pipeline could not be saved")
            
        # If the user specifies a starting index use it, otherwise start at the 
        # first step unless the user specified to resume where it left off
        if start_idx is not None:
            self.run_step_idx = start_idx
        elif not resume:
            self.run_step_idx = 0
        # Run each step in order
        steps = self.run_steps[self.run_step_idx:]
        for step in steps:
            logger.info('running step {0}: {1}'.format(step.step_id, step.tags))
            # Run the step
            if step._step_type=='PipelineStep':
                func_kwargs = self.get_func_kwargs(step)
                step = run_step(
                    (step, func_kwargs, self.run_step_idx, ignore_errors, ignore_exceptions))
            elif step._step_type=='MultiprocessStep':
                import multiprocessing
                pool_kwargs = {'processes': step.pool_size}
                if step.initializer is not None:
                    pool_kwargs['initializer'] = step.initializer
                pool = multiprocessing.Pool(** pool_kwargs)
                pool_params = []
                for mstep in step.steps:
                    func_kwargs = self.get_func_kwargs(mstep)
                    pool_params.append(
                        (mstep, func_kwargs, self.run_step_idx, ignore_errors, ignore_exceptions)
                    )
                pool_results = pool.map(run_step, pool_params)
                pool.close()
                pool.join()
                step.steps = pool_results
                if all([s.results['status']=='success' for s in step.steps]):
                    step.results = {
                        'status': 'success'
                    }
                elif all([s.results['status']=='error' for s in step.steps]):
                    step.results = {
                        'status': 'error'
                    }
                else:
                    step.results = {
                        'status': 'some failed'
                    }
            # Increase the run_step_idx and save the pipeline
            self.run_step_idx+=1
            if not skip_save:
                self.save_pipeline(logfile, dump_type)
        result = {
            'status': 'success'
        }
        return result

class PipelineStep:
    """
    A single step in the pipeline. This takes a function and a set of tags and kwargs
    associated with it and stores them in the pipeline.
    """
    def __init__(self, func, step_id=None, tags=[], ignore_errors=False, ignore_exceptions=False, 
            func_kwargs={}):
        """
        Initialize a PipelineStep object
        
        Parameters
        ----------
        func: function
            The function to be run. All functions must return a dictionary with at a 
            minimum a ``status`` key whose value is either ``success`` or ``error``.
        step_id: str
            Unique identifier for the step
        tags: list (optional)
            A list of tags used to identify the step. When running the pipeline the user
            can specify a set of conditions that will filter which steps are run (or not run)
            based on a set of specified tags
        ignore_errors: bool (optional)
            If ``ignore_errors==False`` the pipeline will raise an exception if an error
            occurred during this step in the pipeline, which returned a result with
            ``result['status']=='error'``. The default is ``False``.
        ignore_exceptions: bool (optional)
            If ``ignore_exceptions==True`` the pipeline will set ``result['status']=='error'``
            for the step that threw an exception and continue running. The default is
            ``ignore_exceptions==False``, which will stop the pipeline and raise an
            exception.
        func_kwargs: dict
            Keyword arguments passed to the ``func`` when the pipeline is run
            
            .. warning::
            
                There are a few protected keywords:
                    - ``global_vars``: global variables for all steps in the pipeline
                    - ``pipeline``: the entire pipeline is passed to the function
        """
        self._step_type = 'PipelineStep'
        self.func = func
        self.tags = tags
        self.step_id = step_id
        self.ignore_errors = ignore_errors
        self.ignore_exceptions = ignore_exceptions
        self.func_kwargs = func_kwargs
        self.results = None

class MultiprocessStep(StepContainer):
    """
    A collection of steps to be run concurrently on a multiple cores.
    
    .. warning::
    
        It might not be possible to pass a `.Pipeline` object to a function in
        a MultiprocessStep because pipelines may contain non-picklable objects.
        Keep this in mind when creating functions for MultiprocessSteps.
    """
    def __init__(self, step_id=None, tags=list(), steps=list(), pool_size=None, 
            initializer=None, finalizer=None, next_id=0):
        """
        Initialize a MultiprocessStep
        
        Parameters
        ----------
        step_id: str
            Unique identifier for the step
        tags: list (optional)
            A list of tags used to identify the step. When running the pipeline the user
            can specify a set of conditions that will filter which steps are run (or not run)
            based on a set of specified tags
        steps: list-like (optional)
            A list of steps to be run concurrently. Each element of the list should be a
            :class:`.PipelineStep` or a dictionary of parameters used for each step.
            If no steps are specified they can be added later by the user
        pool_size: int (optional)
            Number of concurrent processors to use
        initializer: func (optional)
            Function to run to when pools are initialized
        finalizer: func (optional)
            Function to run when the pools have finished
        """
        import multiprocessing
        self._step_type = 'MultiprocessStep'
        self.step_id = step_id
        self.tags = tags
        self.next_id = next_id
        
        # Set the number of processors to use
        if pool_size is None:
            pool_size = multiprocessing.cpu_count()
            logger.info('Using {0} workers'.format(pool_size))
        self.pool_size = pool_size
        
        # Set the initialization function
        self.initializer = initializer
        self.steps = []
        # Check whether each step is a PipelineStep or a dict-like object
        for step in steps:
            if isinstance(step, PipelineStep):
                self.steps.append(step)
            else:
                self.steps.append(PipelineStep(**step))
    
    def get_next_id(self):
        new_id = str(self.step_id)+'-'+str(self.next_id)
        self.next_id += 1
        return new_id

class PipelineGlobals:
    """
    Global variables for a pipeline. These are variables that can be modified by each step
    
    .. warning::
    
        If the current step is a `.MultiprocessStep` the same value of each variable in
        PipelineGlobals is passed to each step in the pipeline. Since multiple functions
        will be running copies of the same variable in separate processes, any changes
        made to a pipeline global variable in any one of these steps will *not* be
        saved in the pipeline. In other words, a PipelineGlobals variable can be 
        loaded but not changed by a MultiprocessStep.
    """
    def __init__(self, **kwargs):
        for k,v in kwargs:
            setattr(self,k,v)