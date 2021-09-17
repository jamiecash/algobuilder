import logging
from celery import shared_task
from feature import feature


@shared_task(name='calculate_feature', queue='feature')
def calculate_feature(feature_id: int):
    """
    Executes the feature calculation for all feature_executions attached to the specified feature
    :param feature_id:
    :return:
    """
    from feature import models  # Imported when needed, due to circular dependency

    # Logger
    log = logging.getLogger(__name__)

    # Get the feature
    feature_model = models.Feature.objects.get(id=feature_id)

    # Continue if active
    if feature_model.active:
        log.debug(f"Running task to calculate feature {feature_model.name}.")
        # Get the implementation
        feature_impl = feature.FeatureImplementation.instance(feature_model.name)

        # Execute all active feature executions
        for feature_execution in feature_model.featureexecution_set.all():
            if feature_execution.active:
                # Execute
                log.debug(f"Running FeatureExecution {feature_execution}.")
                feature_impl.execute(feature_execution)
            else:
                log.debug(f"Not running FeatureExecution {feature_execution}. It is inactive.")
    else:
        log.debug(f"Task to calculate feature {feature_model.name} did not run as feature is inactive.")

