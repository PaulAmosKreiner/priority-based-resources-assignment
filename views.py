import pandas as pd
import numpy as np
from scipy.optimize import linprog

import hashlib
from random import randint

from flask import Blueprint, request, render_template, flash, Response

from wtforms import Form
from wtforms.fields import SelectField, TextAreaField, IntegerField, StringField

prioritybasedresourcesassignment = Blueprint('prioritybasedresourcesassignment', __name__, template_folder='templates')

@prioritybasedresourcesassignment.route('/', methods=["POST","GET"])
def create():

    class CreateForm(Form):
        options = TextAreaField(
            label='list all the options here, semicolon-separated',
        )
        #n_preferences = IntegerField(
        #    label='how many preferences everyone should be required to submit',
        #    default=3,
        #)
        language = SelectField(
            label='language',
            choices=["de", "en"]
        )

    form = CreateForm(request.form)

    if request.method == "POST":

        options = form.options.data.split(";")
        language = form.language.data
        #n_preferences = form.n_preferences.data

        try:
            assignmentprocesses = pd.read_pickle("database.pkl")
        except:  # noqa
            assignmentprocesses = pd.DataFrame(columns=["language",
                                                        #"n_preferences",
                                                        "options",
                                                        "finish_key",
                                                        "participation"
                                                        ])

        # finding a key for this

        full_hash = hashlib.md5(str(options).encode()).hexdigest()
        found_nonduplicate_hash = False
        key_kandidate = full_hash[:5]
        it = 1
        while not found_nonduplicate_hash:
            if key_kandidate in assignmentprocesses.keys():
                key_kandidate = full_hash[it:it+5]
            else:
                found_nonduplicate_hash = True
        key = key_kandidate

        finish_key = randint(1000, 9999)

        assignmentprocesses.loc[key] = {"language": language,
                                        "options": options,
                                        #"n_preferences": n_preferences,
                                        "finish_key": str(finish_key),
                                        "participation": {}
                                        }

        # persist

        assignmentprocesses.to_pickle("database.pkl", protocol=4)

        # out the link

        parti_link = request.url + key
        finish_link = parti_link + "/finish/" + str(finish_key)
        return \
            "participation link is: <a href='" + parti_link + "'>" + \
            parti_link + "</a>.<br>" + \
            "link for finishing up is: <a href='" + finish_link + "'>" + \
            finish_link + "</a>." + \
            "save them somewhere, you won't be able to access them again."

    return render_template('prioritybasedresourcesassignment/main.html',
                           form=form)


@prioritybasedresourcesassignment.route('/<key>', methods=["POST", "GET"])
def submit_preferences(key):

    try:
        assignmentprocesses = pd.read_pickle("database.pkl")
        process = assignmentprocesses.loc[key]
    except:  # noqa
        return Response(status=404)

    class PreferencesForm(Form):
        name = StringField(
            label="name",
        )
        first_pref = SelectField(
            label="1.",
            choices=process.options,
        )
        second_pref = SelectField(
            label="2.",
            choices=process.options,
        )
        third_pref = SelectField(
            label="3.",
            choices=process.options,
        )

    form = PreferencesForm(request.form)

    if request.method == "GET":

        # TODO mehrfachauswahl nicht erlaubt

        return render_template('prioritybasedresourcesassignment/main.html',
                               form=form)

    else:  # post

        name = form.name.data
        first_pref = form.first_pref.data
        second_pref = form.second_pref.data
        third_pref = form.third_pref.data

        # TODO will overwrite on identical name

        process.participation[name] = [first_pref,second_pref,third_pref]

        assignmentprocesses.to_pickle("database.pkl", protocol=4)

        return "successfully submitted" if process.language == "en" else \
            "erfolgreich übermittelt"




@prioritybasedresourcesassignment.route('/<key>/finish/<finish_key>', methods=["GET"])
def calculate_result(key, finish_key):

    try:
        assignmentprocesses = pd.read_pickle("database.pkl")
        process = assignmentprocesses.loc[key]
        assert finish_key == process.finish_key
    except:  # noqa
        return Response(status=404)

    p = pd.DataFrame(
        0,
        columns=process.participation.keys(),
        index=process.options
    )

    preflookup = {
        0: 3,
        1: 2,
        2: 1
    }
    for who, prefers in process.participation.items():
        for pref in range(len(prefers)):
            p.at[prefers[pref], who] = preflookup[pref]

    print(process)

    import warnings
    warnings.filterwarnings("ignore")

    ineq_constraints = []

    # constraining max 1 assignment per person
    wished = (p != 0).astype(int)
    for col in wished.columns:
        constraint = wished.copy()
        for other_col in [other_col for other_col in wished.columns if
                          other_col != col]:
            constraint[other_col] = 0
        ineq_constraints += [constraint.values.flatten()]

    # constraining max 1 assignment per selectable
    present = p.notna().astype(int)
    for row in present.index:
        constraint = present.copy()
        for other_row in [other_row for other_row in wished.index if
                          other_row != row]:
            constraint.loc[other_row] = 0
        ineq_constraints += [constraint.values.flatten()]

    ineq_constraints = np.array(ineq_constraints)  # <= 1

    ineq_vector = np.ones(shape=np.sum(p.shape)).astype(int)

    bounds = (0, 1)

    res = linprog(
        c=-p.values.flatten(),
        A_ub=ineq_constraints,
        b_ub=ineq_vector,
        # A_eq=eq_constraints,
        # b_eq=eq_vector,
        bounds=bounds,
        method="revised simplex",
        options={"autoscale": True}
    )

    result = pd.DataFrame(res.x.round().reshape(p.shape), columns=p.columns,
                          index=p.index).astype(int)

    # TODO path anpassen
    template_path = "prioritybasedresourcesassignment/templates/prioritybasedresourcesassignment/"
    out_html = open(template_path + "head.html").read()
    out_html += "<p>unassigned persons: " + \
               str(result.columns[result.sum() != 1].values) + \
               "</p><p>unassigned selectables: " + \
               str(result.index[result.sum(axis=1) != 1].values) + "</p>"
    out_html += "<br>"
    out_html += result.to_html()

    return out_html
