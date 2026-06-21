from flask import jsonify


def error_response(code: str, message: str, status_code: int):
    return jsonify({'error': {'code': code, 'message': message}}), status_code


def bad_request(message: str):
    return error_response('BAD_REQUEST', message, 400)


def unauthorized(message: str = 'Authentication required'):
    return error_response('UNAUTHORIZED', message, 401)


def forbidden(message: str = 'Access denied'):
    return error_response('FORBIDDEN', message, 403)


def not_found(message: str = 'Resource not found'):
    return error_response('NOT_FOUND', message, 404)


def conflict(message: str):
    return error_response('CONFLICT', message, 409)


def unprocessable(message: str):
    return error_response('UNPROCESSABLE', message, 422)


def server_error(message: str = 'An unexpected error occurred'):
    return error_response('INTERNAL_ERROR', message, 500)
