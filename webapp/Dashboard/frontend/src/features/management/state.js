'use strict';

let managementTab = 'overview';
let managementData = null;
let managementPoll = null;
let managementPending = false;
let trainingReference = 'm9';
const managementTabs = {overview:'Overview',feedback:'Feedback',train:'Train & Tune',registry:'Model Registry'};
const dateText = value => value ? localDay.format(new Date(value))+' '+time(new Date(value))+' ICT' : 'Not recorded';

function managedButton(label, action, value, css='btn') {
  return '<button type="button" class="'+css+'" data-management="'+action+'" data-value="'+escape(value)+'">'+label+'</button>';
}
