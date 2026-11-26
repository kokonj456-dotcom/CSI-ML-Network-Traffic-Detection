'use strict';

let managementTab = 'overview';
let managementData = null;
let managementPoll = null;
let managementPending = false;
let trainingReference = 'baseline';
let trainingStrategy = 'class_weighted';
const managementTabs = {overview:'Overview',feedback:'Feedback',train:'Train & Tune',registry:'Model Registry'};
const trainingStrategies = {
  baseline:{label:'Baseline · no class weighting or resampling',short:'Baseline',help:'Train on CENTRAL Train as-is, without class weights or synthetic samples.'},
  class_weighted:{label:'Class weighting · balanced weights',short:'Class weighting',help:'Apply balanced class weights to both attack detection and category classification. This is the current default.'},
  smotenc:{label:'SMOTENC · resampled training data',short:'SMOTENC',help:'Train with the prepared CENTRAL SMOTENC split. Feedback is added to the selected training data.'},
  compare:{label:'Compare all 3 · automatic selection',short:'Compare all 3',help:'Train Baseline, Class weighting, and SMOTENC candidates, then select one using validation FPR, category macro F1, and binary F1. This takes longer.'}
};
const dateText = value => value ? localDay.format(new Date(value))+' '+time(new Date(value))+' ICT' : 'Not recorded';

function managedButton(label, action, value, css='btn') {
  return '<button type="button" class="'+css+'" data-management="'+action+'" data-value="'+escape(value)+'">'+label+'</button>';
}
