from shared_auth import get_current_user_id, verifier_from_env

get_current_user_id_dep = get_current_user_id(verifier_from_env())
